#!/usr/bin/env bash
# Sprawdzenie stanu srodowiska. Uruchamianie: make doctor
# Weryfikuje narzedzia, klucze JWT, konfiguracje compose, wystawianie tokenu oraz to, czy dzialajacy
# gateway odrzuca ruch bez tokenu i przyjmuje token poprawny. Nie zmienia stanu stosu.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

pass=0; warn=0; fail=0
# QUIET=1 (uzywane przez `make jury`) pokazuje tylko ostrzezenia, bledy i podsumowanie.
# Pelna lista sprawdzen jest dostepna przez: make doctor
QUIET="${QUIET:-0}"
sec(){ [[ "$QUIET" == "1" ]] || echo "== $1 =="; }
ok(){ pass=$((pass+1)); [[ "$QUIET" == "1" ]] || printf '  OK    %-32s %s\n' "$1" "$2"; }
wn(){ warn=$((warn+1)); printf '  OSTRZ %-32s %s\n' "$1" "$2"; }
no(){ fail=$((fail+1)); printf '  BLAD  %-32s %s\n' "$1" "$2"; }

sec "narzedzia"
command -v docker  >/dev/null && ok "docker"  "$(docker --version 2>/dev/null | cut -d, -f1)" || no "docker" "nie znaleziono"
command -v go      >/dev/null && ok "go"      "$(go version 2>/dev/null | awk '{print $3}')" || wn "go" "nie znaleziono - potrzebne dla scripts/token.sh"
command -v openssl >/dev/null && ok "openssl" "$(openssl version 2>/dev/null | awk '{print $1, $2}')" || wn "openssl" "nie znaleziono - potrzebne dla make keys"

sec "klucze JWT"
for f in gateway/keys/jwt.key gateway/keys/jwt.pub; do
  if   [[ -f "$f" ]]; then ok "$f" "plik klucza"
  elif [[ -d "$f" ]]; then no "$f" "katalog zamiast pliku (docker tworzy go, gdy montuje nieistniejacy plik): rm -rf $f && make keys"
  else                     no "$f" "brak - uruchom: make keys"
  fi
done

if [[ -x gateway/bin/mint ]]; then ok "gateway/bin/mint" "zbudowany (wystawianie tokenu dziala tez pod sudo)"
else wn "gateway/bin/mint" "brak - uruchom: make mint-build (bez tego wymagane jest go)"; fi

sec "konfiguracja compose"
# Bez --profile polecenie docker compose config pomija serwisy z profilami (tests, benchmarks, java, semantic).
profiles=(--profile tests --profile bench --profile semantic --profile java)
if docker compose "${profiles[@]}" config --quiet 2>/dev/null; then
  ok "docker compose config" "poprawna (z profilami)"
else
  no "docker compose config" "niepoprawna - uruchom: docker compose ${profiles[*]} config"
fi
# Nadpisanie Ollamy musi wskazywac istniejace serwisy. Literowka w nazwie tworzy serwis bez obrazu
# i psuje `make ollama-up` dopiero w trakcie pokazu - dlatego sprawdzamy to przed startem.
if docker compose -f docker-compose.yaml -f docker-compose.ollama.yaml config --quiet 2>/dev/null; then
  ok "docker compose config (ollama)" "poprawna"
else
  no "docker compose config (ollama)" "niepoprawna - uruchom: docker compose -f docker-compose.yaml -f docker-compose.ollama.yaml config"
fi

sec "sekrety lokalne"
if [[ -f .env ]]; then
  if grep -qE '^[A-Z_]*(API_KEY|TOKEN|SECRET)=sk-[A-Za-z0-9_-]{20,}' .env 2>/dev/null; then
    wn ".env" "zawiera klucz API (sk-...). Git go ignoruje i nigdy nie byl commitowany, ale ZIP lub kopia katalogu zabierze go ze soba - usun klucz albo trzymaj plik poza repo"
  else
    ok ".env" "obecny, bez rozpoznanego klucza API"
  fi
else
  ok ".env" "brak - uzywane sa wartosci domyslne z docker-compose"
fi
if git ls-files --error-unmatch .env >/dev/null 2>&1; then no ".env w git" "plik JEST sledzony - usun go z repozytorium i uniewaznij klucze"
else ok ".env w git" "nie jest sledzony"; fi


sec "token"
if [[ -f gateway/keys/jwt.key ]] && command -v go >/dev/null; then
  tok="$(./scripts/token.sh 2>/dev/null || true)"
  if [[ -n "$tok" ]]; then
    payload="$(cut -d. -f2 <<<"$tok" | sed 's/-/+/g; s/_/\//g')"
    pad=$(( (4 - ${#payload} % 4) % 4 ))
    [[ $pad -gt 0 ]] && payload+="$(printf '=%.0s' $(seq 1 $pad))"
    claims="$(printf '%s' "$payload" | base64 -d 2>/dev/null || true)"
    if [[ -n "$claims" ]]; then
      ok "wystawianie tokenu" "$(sed -nE 's/.*"iss":"([^"]+)".*/iss=\1/p; s/.*"sub":"([^"]+)".*/sub=\1/p' <<<"$claims" | tr '\n' ' ')"
    else
      wn "wystawianie tokenu" "token powstaje, ale nie udalo sie odczytac jego zawartosci"
    fi
  else
    no "wystawianie tokenu" "scripts/token.sh zakonczyl sie bledem"
  fi
else
  wn "wystawianie tokenu" "pominiete (brak klucza lub brak go)"
fi

sec "dzialajacy gateway"
code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{"model":"mock-llm","messages":[]}' 2>/dev/null)"
case "${code:-000}" in
  401|403) ok "ruch bez tokenu odrzucony" "$code" ;;
  000)     wn "osiagalnosc gatewaya" "nie dziala: sudo docker compose up -d gateway" ;;
  200)     wn "ruch bez tokenu odrzucony" "200 - uruchomiona wersja nie wymaga jeszcze tokenu, przebuduj: sudo docker compose up -d --build gateway" ;;
  *)       wn "ruch bez tokenu odrzucony" "nieoczekiwany kod $code" ;;
esac

# Token poprawny musi byc przyjety. Ten test wykrywa przypadek, w ktorym dzialajacy kontener ma inny
# klucz publiczny niz biezacy plik gateway/keys/jwt.pub (na przyklad po ponownym wygenerowaniu kluczy).
tok="$(./scripts/token.sh 2>/dev/null || true)"
if [[ -z "$tok" ]]; then
  wn "token przyjety przez gateway" "pominiete (nie udalo sie wystawic tokenu)"
else
  acc="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST http://localhost:8080/v1/chat/completions \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $tok" \
    -d '{"model":"mock-llm","messages":[{"role":"user","content":"doctor"}]}' 2>/dev/null)"
  case "${acc:-000}" in
    200)     ok "token przyjety przez gateway" "200" ;;
    401|403) no "token przyjety przez gateway" "$acc - dzialajacy gateway ma inny klucz publiczny niz gateway/keys/jwt.pub; uruchom: sudo docker compose up -d --force-recreate gateway" ;;
    503)     wn "token przyjety przez gateway" "503 - polityka nie zostala wczytana z control plane" ;;
    000)     wn "token przyjety przez gateway" "gateway nieosiagalny" ;;
    *)       wn "token przyjety przez gateway" "nieoczekiwany kod $acc" ;;
  esac
fi

echo
echo "doctor: $pass ok, $warn ostrzezen, $fail bledow"
[[ "$fail" -eq 0 ]]
