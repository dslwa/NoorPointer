# Testy kontroli AI

Pakiety osobno sprawdzają kontrakt Pythona, jakość prawdziwych modeli i egzekwowanie kontroli przez
gateway. Poprawny wynik detektora nie dowodzi, że gateway wywołuje go na odpowiedziach LLM.

Wyniki wykonanej walidacji i wykryte braki: [VALIDATION.md](VALIDATION.md).

## Testowanie teraz, bez zmian Go i gRPC

W przygotowanym środowisku tego repozytorium uruchom z katalogu głównego:

```bash
./scripts/test-without-go.sh
```

Polecenie sprawdza szybki pakiet Pythona, importer sygnatur, schematy/profilowanie polityk Javy,
testy dashboardu i jego build. Wymaga `semantic-service/.venv` (`uv sync`), Javy 21, Maven,
Node/npm i zależności panelu (`cd dashboard && npm ci`). Nie uruchamia Go ani nie zmienia
aktywnej polityki. Pełne testy Javy, także API/audyt, wymagają osobnej bazy `noorpointer_test`:
`make postgres-test-up`, następnie w `controlplane`: `mvn -B -ntp -Dfrontend.skip=true test`.

**Nie publikuj profili `*-output` do obecnego Go.** Są gotowe do walidacji/draftów po stronie Javy,
ale jego parser jeszcze ich nie obsługuje. Uzgodnienia pozostawione dla Go:
[GO_HANDOFF.md](GO_HANDOFF.md). Działające kontenery nie są aktualizowane przez ten skrypt.

## 1. Kontrakt HTTP/gRPC — bez modeli

Z katalogu `semantic-service`:

```bash
uv sync
uv run pytest -q --junitxml=/tmp/semantic.xml
```

`tests/test_output_contract.py` uruchamia rzeczywisty serwer i klienta gRPC, adapter content safety
i detektor leakage. Zastępuje inferencję PII oraz odpowiedzi Ollamy kontrolowanymi wynikami. Sprawdza:

- bezpieczne i niebezpieczne odpowiedzi, osobno oraz z kilkoma trafieniami;
- `system` i `user` jako kontekst OUTPUT, `assistant` i `tool` jako cele skanu;
- wszystkie wiadomości systemowe oraz ostatnią wiadomość użytkownika w kontekście;
- dokładnie jeden wynik na parę wiadomość–kontrola, również przy powtórzonym `CheckSpec`;
- `STATUS_ERROR`, `STATUS_TIMEOUT`, `STATUS_REJECTED` bez utraty poprawnych wyników innych kontroli;
- offsety PII w **bajtach UTF-8**: emoji i polskie znaki przed encją oraz wewnątrz encji;
- canary wprost i w Base64, kategorie content safety i odrzucanie zbyt dużych odpowiedzi.

To sprawdzenie protokołu i obsługi awarii. Jakość modeli mierzy kolejny pakiet.

## 2. Prawdziwe DeBERTa, spaCy i Llama Guard

Z katalogu `semantic-service`:

```bash
MODELS_OFFLINE=1 uv run pytest -m 'models and not ollama' -q \
  --junitxml=/tmp/models.xml -o junit_family=legacy

OLLAMA_URL=http://localhost:11434 GUARD_CONCURRENCY=1 uv run pytest -m ollama -q \
  --junitxml=/tmp/ollama.xml -o junit_family=legacy
```

`MODELS_OFFLINE=1` wymaga wcześniej pobranego modelu DeBERTa. Brak cache jest błędem testu;
nie ustawiaj tej zmiennej przy pierwszym uruchomieniu, jeśli model ma zostać pobrany.
`uv sync` instaluje modele spaCy wymagane przez projekt.

W podstawowym Compose port `11434` obsługuje **mock-llm**. W profilu
`docker-compose.ollama.yaml` prawdziwa Ollama jest dostępna wewnątrz sieci Dockera jako
`ollama:11434`. Test musi mieć dostęp do tej sieci lub do innej lokalnej Ollamy z modelem
`llama-guard3:1b`. Fixture odrzuca pozorny rozmiar/digest modelu z mocka zamiast pozorować pomiar jakości.
Na obecnym hoście adres kontenera można uzyskać poleceniem
`docker compose -f docker-compose.yaml -f docker-compose.ollama.yaml exec -T ollama hostname -i`
i ustawić `OLLAMA_URL=http://<adres>:11434`. Nie zakładaj stałego adresu IP.
Przypadki Llama Guard wymagają zakończenia kontroli w 15 s; timeout nie oznacza wykrycia ataku.

Przypadki obejmują polskie zdania, znaczniki `[REDACTED:...]`, PII w OUTPUT, injection z zamaskowanym
PII, bezpieczną odmowę na niebezpieczne pytanie i szkodliwą odpowiedź na bezpieczne pytanie PL/EN.
JUnit zapisuje score DeBERTa oraz model, digest, kategorie i czas kontroli Llama Guard.
To niewielki zestaw regresyjny, nie reprezentatywna ocena całego języka polskiego.

Istniejący przypadek zwykłej prośby o zwrot na kartę pozostaje `xfail(strict=True)` z powodu
udokumentowanego fałszywego alarmu DeBERTa. Braki gatewaya nie są oznaczane `xfail`.

## 3. Izolowany gateway: OUTPUT, hot-reload, powtórzenia narzędzi

Z katalogu głównego, na Linuksie, z Dockerem i uruchomionym serwisem semantycznym:

```bash
python3 -m venv .venv-tests
.venv-tests/bin/pip install -r tests/requirements.txt
.venv-tests/bin/python tests/run_gateway_acceptance.py --build \
  --junitxml=/tmp/gateway-acceptance.xml
```

Runner buduje aktualny Go do osobnego obrazu `noorpointer-gateway:acceptance`, wypisuje jego ID,
kopiuje binarkę do katalogu tymczasowego i uruchamia `test_gateway_acceptance.py`. Nie zmienia
kodu Go ani działającego gatewaya. Nie wymaga toolchaina Go ani ręcznego wystawiania JWT.
Bez `--build` wykorzystuje już zbudowany obraz. Wariant bez Dockera:

```bash
GATEWAY_BINARY=/absolute/path/to/gateway \
SEMANTIC_GRPC_URL=127.0.0.1:50051 \
.venv-tests/bin/python -m pytest tests/test_gateway_acceptance.py -v
```

Każdy test dostaje osobny proces gatewaya, klucz RSA/JWT oraz lokalny serwer HTTP udostępniający
politykę i kontrolowaną odpowiedź modelu. Korzysta z istniejącego serwisu semantycznego przez gRPC
(`SEMANTIC_GRPC_URL`, domyślnie `127.0.0.1:50051`). Publikację polityk w Javie sprawdza punkt 4.

- Redakcja wejścia jest sprawdzana w treści rzeczywiście odebranej przez model.
- Model odpowiada na bezpieczny prompt treścią z PII, syntetycznym sekretem, niebezpieczną instrukcją
  albo tekstem system promptu. Test potwierdza, że model dostał żądanie: blokada wejścia nie może
  zastąpić dowodu filtrowania OUTPUT.
- Hot-reload zmienia `redact → block → redact` dla tej samej treści. Asercje sprawdzają
  HTTP `200 → 403 → 200`, wersję polityki i brak zablokowanego żądania w modelu, bez restartu gatewaya.
- Pętla to rzeczywiste kolejne żądania z rosnącą historią `tool_calls`. Każdy `call_id` jest nowy,
  lecz nazwa i argumenty funkcji się powtarzają. Wariant pozytywny zmienia argumenty.
  `X-Session-ID` koreluje rozmowę; nie przekazuje rzekomej liczby powtórzeń.
  Przy limicie 3 akceptujemy blokadę na trzecim lub czwartym wywołaniu, ale nie na pierwszym.
- Feed: rzeczywisty plik sygnatur blokuje wskaźnik w prompcie/argumentach narzędzia, nie blokuje
  go w niewłaściwym polu; `first|second` jest zachowane dosłownie. Wyłączenie i ponowne włączenie
  reguły po reloadzie zmienia wynik żądania.

Polityka testowa wyłącza prompt injection, aby znane fałszywe alarmy na legalnych instrukcjach
systemowych nie uniemożliwiały oceny OUTPUT. W przypadkach pętli wyłącza też content safety.
Jakość detektorów mierzy punkt 2. Kontrole PII/secrets i content safety w przypadkach OUTPUT są aktywne.
Test wycieku system promptu opisuje oczekiwane zachowanie; schemat gatewaya nie ma jeszcze osobnej
konfiguracji tej kontroli. Obsługa strumieniowania i wszystkich formatów odpowiedzi nie jest tu testowana.

Brak implementacji zabezpieczenia daje **FAIL**, nawet jeżeli pakiet Pythona przechodzi.

Budżety: dodaj `--budgets`, aby uruchomić również `test_gateway_budgets.py` (8 przypadków):

```bash
semantic-service/.venv/bin/python tests/run_gateway_acceptance.py --budgets
```

Pakiet używa podpisanych JWT, prawdziwych powtórzeń wywołań i 12 współbieżnych żądań. Sprawdza
liczbę żądań odebranych przez kontrolowany model i rzeczywiste wartości jego `usage`, niezależność
agentów, wspólny limit zespołu/modelu oraz próbę podmiany tożsamości w JSON/nagłówkach.
Koszt API i czas GPU są **symulowaną telemetrią zaufanego providera**: założenie do integracji,
opisane w [GO_HANDOFF.md](GO_HANDOFF.md), nie pomiar rzeczywistego GPU/rachunku dostawcy.

## 4. E2E działającego stosu, w tym control plane Java

```bash
make test         # kontener, raport HTML w reports/
make test-local   # lokalny pytest, opublikowane porty
```

Polecenia przekazują JWT przez `scripts/token.sh` (wymaga Go lub zbudowanego `gateway/bin/mint`).
Bezpośrednio: ustaw `GATEWAY_JWT` i uruchom `pytest tests/test_guardrails.py -v`.
Konfiguracja: `GATEWAY_URL`, `SEMANTIC_URL`, `CONTROLPLANE_URL`, `CHAT_MODEL`,
`ADMIN_TOKEN`, `GATEWAY_TOKEN`, `REQUEST_TIMEOUT` (domyślnie 30 s).

**Używaj stosu testowego bez równoległych edycji polityki.** Hot-reload publikuje tymczasowe rewizje
w Javie, sprawdza zmianę decyzji i w `finally` przywraca pierwotną rewizję oraz usuwa swoje rewizje.
Nie nadpisuje wykrytej obcej zmiany. Na czas testu kontroli PII wyłącza prompt injection i content
safety. Przerwanie procesu bez wykonania `finally` wymaga ręcznego przywrócenia polityki.

Test budżetu 0 publikuje limit dla `sub` rzeczywistego JWT i przywraca politykę w `finally`.
Nie używa nazwy agenta w JSON jako dowodu tożsamości; zużywanie niezerowego limitu i wyścigi
sprawdza pakiet izolowany. Wyniki zależą od konfiguracji, dostępności
modeli i implementacji gatewaya. `503 SEMANTIC_UNAVAILABLE` oznacza problem dostępności, a nie
poprawne wykrycie ataku. Test odpowiedzi na prompt z PII nie zakłada, że model powtórzy znacznik
redakcji — właściwy dowód redakcji przed wysłaniem do modelu daje pakiet izolowany.
