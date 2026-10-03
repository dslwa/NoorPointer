#!/usr/bin/env bash
# Kopia bazy audytu do backups/. Uruchamianie: make db-dump   (wymaga sudo - pg_dump w kontenerze)
# Format custom, zeby dalo sie odtworzyc przez `make db-restore FILE=...`. OUT=sciezka zmienia miejsce.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
mkdir -p backups

out="${1:-${OUT:-}}"
[[ -n "$out" ]] || out="backups/noorpointer-$(date -u '+%Y%m%dT%H%M%SZ').dump"

if ! $COMPOSE ps postgres --status running >/dev/null 2>&1; then
  echo "db-dump: kontener postgresa nie dziala - uruchom: make up" >&2
  exit 1
fi

$COMPOSE exec -T postgres pg_dump -U noor -d noorpointer --format=custom > "$out"
echo "db-dump: zapisano $out ($(du -h "$out" | cut -f1))"
