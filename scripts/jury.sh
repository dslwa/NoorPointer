#!/usr/bin/env bash
# JEDNO polecenie dla osoby oceniajacej: sprawdza srodowisko, buduje i uruchamia stos, uruchamia
# wszystkie testy, generuje ruch na panele i zbiera dowody do katalogu dowody/.
#
# Kroki testowe nie przerywaja calosci: jesli cos nie przejdzie, zobaczysz to w podsumowaniu,
# a reszta i tak sie wykona po to, zebys mial pelny obraz stanu.
#
# Uzycie: sudo make jury
set -uo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
failed=()

run() {
  local opis="$1"
  shift
  step "$opis"
  if ! "$@"; then failed+=("$opis"); fi
}

step "0/7 Narzedzia, klucze i konfiguracja"
./scripts/doctor.sh || true

step "1/7 Buduje obrazy i uruchamiam stos (pierwsze uruchomienie moze potrwac kilka minut)"
if ! make up; then
  echo "jury: nie udalo sie uruchomic stosu - dalsze kroki nie maja sensu" >&2
  exit 1
fi

run "2/7 Testy jednostkowe modulow (Go)" make test-unit
run "3/7 Testy modulowe (Java, w kontenerze, na osobnej bazie)" make controlplane-test
run "4/7 Testy e2e (16 przypadkow)" make test
run "5/7 Ruch na panele Grafany" ./scripts/traffic.sh
run "6/7 Dowody do katalogu dowody/" make evidence

step "7/7 Podsumowanie i co dalej"
./scripts/jury-next-steps.sh

if [[ ${#failed[@]} -gt 0 ]]; then
  printf '\nKroki zglaszajace blad (szczegoly wyzej): %s\n' "$(IFS=', '; echo "${failed[*]}")"
  echo "To nie znaczy, ze wszystko jest zepsute - sekcja 'Czego jeszcze nie ma' w START.md wyjasnia,"
  echo "ktore kontrole sa w trakcie implementacji."
fi
exit 0
