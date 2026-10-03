#!/usr/bin/env bash
# Przywraca dane demonstracyjne do stanu z repozytorium. Uruchamianie: make db-tidy (wymaga sudo).
# Czysci dziennik zdarzen, usuwa zdublowane wersje zasad i wpisy sygnatur, ktorych nie ma
# w zadnym zrodle. Czyszczenie dziennika pominiesz przez SKIP_AUDIT=1.

set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"

psql() { $COMPOSE exec -T postgres psql -U noor -d noorpointer -v ON_ERROR_STOP=1 "$@"; }

if ! $COMPOSE ps postgres --status running >/dev/null 2>&1; then
  echo "db-tidy: kontener postgresa nie dziala - uruchom: make up" >&2
  exit 1
fi

echo "== przed sprzatnieciem =="
psql -At -c "SELECT 'zdarzenia audytu: ' || count(*) FROM controlplane.audit_event;"
psql -At -c "SELECT 'rewizje polityki: ' || count(*) FROM controlplane.policy_revision;"
psql -At -c "SELECT 'sygnatury w katalogu: ' || count(*) FROM controlplane.signature;"

if [[ "${SKIP_AUDIT:-0}" == "1" ]]; then
  echo "== 1/3 czyszczenie zdarzen audytu: pominiete (SKIP_AUDIT=1) =="
else
  echo "== 1/3 czyszczenie zdarzen audytu =="
  psql -q -c "TRUNCATE TABLE controlplane.audit_event;"
fi

echo "== 2/3 usuwanie zdublowanych rewizji polityki =="
# Najpierw przepinamy aktywna rewizje na najstarsza w swojej grupie identycznych dokumentow,
# potem kasujemy pozostale duplikaty (poza ta, na ktora wskazuje active_policy).
psql -q -c "
  WITH groups AS (
    SELECT id,
           MIN(id) OVER (PARTITION BY name, md5((document::jsonb - 'version')::text)) AS first_id
    FROM controlplane.policy_revision
  )
  UPDATE controlplane.active_policy a
  SET revision_id = g.first_id
  FROM groups g
  WHERE a.revision_id = g.id AND g.first_id <> g.id;
"
psql -At -c "
  WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY name, md5((document::jsonb - 'version')::text)
             ORDER BY id
           ) AS rn
    FROM controlplane.policy_revision
  )
  DELETE FROM controlplane.policy_revision
  WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    AND id <> (SELECT revision_id FROM controlplane.active_policy)
  RETURNING '  usunieto rewizje: ' || id;
"

echo "== 3/3 przywracanie katalogu sygnatur do stanu z repozytorium =="
known_ids="$(python3 - <<'PY'
import json
import sys

sources = (
    "controlplane/src/main/resources/signatures/defaults.json",
    "signatures-feed/signatures.json",
)
identifiers = []
for path in sources:
    try:
        with open(path) as handle:
            identifiers += [entry["id"] for entry in json.load(handle).get("signatures", [])]
    except FileNotFoundError:
        print(f"db-tidy: pomijam brakujacy {path}", file=sys.stderr)
print(",".join("'" + identifier.replace("'", "''") + "'" for identifier in identifiers))
PY
)"
if [[ -n "$known_ids" ]]; then
  psql -At -c "DELETE FROM controlplane.signature WHERE id NOT IN ($known_ids) RETURNING '  usunieto sygnature: ' || id;"
else
  echo "  brak zrodel sygnatur - pomijam ten krok" >&2
fi

echo "== po sprzatnieciu =="
psql -At -c "SELECT 'zdarzenia audytu: ' || count(*) FROM controlplane.audit_event;"
psql -At -c "SELECT 'rewizje polityki: ' || count(*) FROM controlplane.policy_revision;"
psql -At -c "SELECT 'sygnatury w katalogu: ' || count(*) FROM controlplane.signature;"
psql -At -c "SELECT 'aktywna rewizja: ' || r.id || ' (' || r.name || ')' FROM controlplane.active_policy a JOIN controlplane.policy_revision r ON r.id = a.revision_id;"

code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$CONTROLPLANE_URL/api/v1/active-policy" -H "Authorization: Bearer $ADMIN_TOKEN")"
if [[ "$code" != "200" ]]; then
  echo "db-tidy: uwaga, control plane odpowiada HTTP $code przy odczycie aktywnej polityki" >&2
  exit 1
fi

echo "gotowe. Dane demonstracyjne odtworzysz przez: make seed"
