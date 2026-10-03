#!/usr/bin/env bash
# Odtworzenie bazy z kopii. Uruchamianie: make db-restore FILE=backups/noorpointer-....dump (wymaga sudo)
# UWAGA: nadpisuje dane aplikacji (pg_restore --clean --if-exists). Kopia: `make db-dump`.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
file="${1:-${FILE:-}}"

if [[ -z "$file" || ! -f "$file" ]]; then
  echo "db-restore: podaj plik kopii: make db-restore FILE=backups/noorpointer-....dump" >&2
  if compgen -G "backups/*.dump" >/dev/null; then
    echo "  dostepne kopie:" >&2
    ls -1 backups/*.dump | sed 's/^/    /' >&2
  else
    echo "  brak kopii w backups/ - zrob najpierw: make db-dump" >&2
  fi
  exit 1
fi

if ! $COMPOSE ps postgres --status running >/dev/null 2>&1; then
  echo "db-restore: kontener postgresa nie dziala - uruchom: make up" >&2
  exit 1
fi

echo "db-restore: odtwarzam $file (nadpisuje dane aplikacji)"
set +e
$COMPOSE exec -T postgres pg_restore -U noor -d noorpointer --clean --if-exists --no-owner < "$file"
rc=$?
set -e
# pg_restore: 0 = sukces, 1 = ostrzezenia (np. brak obiektu do usuniecia), >=2 = blad.
if [[ "$rc" -gt 1 ]]; then
  echo "db-restore: pg_restore zakonczyl sie kodem $rc" >&2
  exit "$rc"
fi
echo "db-restore: gotowe. Odswiez panel: sudo docker compose restart controlplane"
