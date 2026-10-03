#!/usr/bin/env bash
# Zapisuje aktualne zasady do pliku policy.local.json, zeby mozna je bylo edytowac w edytorze.
# Nic nie zmienia w systemie. Uzycie: make policy-edit

set -euo pipefail
cd "$(dirname "$0")/.."

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
FILE="${FILE:-policy.local.json}"

if ! curl -s -o /tmp/noorpointer-active-policy.json -m 10 \
  "$CONTROLPLANE_URL/api/v1/active-policy" -H "Authorization: Bearer $ADMIN_TOKEN"; then
  echo "policy-edit: control plane nie odpowiada - uruchom: make up" >&2
  exit 1
fi

python3 - "$FILE" <<'PY'
import json
import sys

target = sys.argv[1]
with open("/tmp/noorpointer-active-policy.json") as handle:
    payload = json.load(handle)

revision = payload.get("revision") or payload
document = revision["document"]
document.pop("version", None)
with open(target, "w") as handle:
    json.dump(document, handle, indent=2, ensure_ascii=False)
    handle.write("\n")
print(f"policy-edit: aktywna rewizja {revision.get('version')} zapisana do {target}")
PY

cat <<'TEXT'

Edytuj plik dowolnym edytorem, a potem opublikuj zmiane:

    make policy-apply

Gateway pobiera polityke co sekunde, wiec zmiana dziala bez restartu i bez przebudowy obrazow.
Przyklady zmian, ktore od razu widac:

  "controls.pii_regex.action":  "redact"  ->  "block"
  "defaults.semantic_timeout_ms": 8000    ->  10000
  "controls.attack_signatures": dopisz wlasna regule (wzor lub fraze)

TEXT
