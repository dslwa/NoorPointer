#!/usr/bin/env bash
# Dodaje nowa sygnature ataku do feedu (regex). Sygnatura jest widoczna od razu, bez restartu.
# Uzycie: make new-signature PATTERN='(/etc/passwd|\.\./)' NAME='Path traversal'
# Zmienne: PATTERN, NAME, ACTION, CATEGORY, TARGET_COMPONENT, CVE, DESCRIPTION, NEW_ID.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIG_FILE="$DIR/signatures.json"

PATTERN="${PATTERN:-HACKATHON_ZERO_DAY_PAYLOAD_TEST}"
NAME="${NAME:-Zero-Day Live Injected Attack Pattern}"
ACTION="${ACTION:-block}"
CATEGORY="${CATEGORY:-LLM01: Prompt Injection}"
TARGET_COMPONENT="${TARGET_COMPONENT:-prompt_filter}"
CVE="${CVE:-CVE-LIVE-EMERGENCY}"
DESCRIPTION="${DESCRIPTION:-Dynamicznie dodana regula podczas prezentacji dla jury.}"
NEW_ID="${NEW_ID:-SIG-$(date +%Y%m%d-%H%M%S)}"

case "$ACTION" in
  block|monitor) ;;
  *) echo "push_new_signature: ACTION musi byc 'block' albo 'monitor' (jest: $ACTION)" >&2; exit 1 ;;
esac

echo "Dodawanie sygnatury $NEW_ID do feedu."

python3 - "$SIG_FILE" "$NEW_ID" "$NAME" "$PATTERN" "$ACTION" "$CATEGORY" "$TARGET_COMPONENT" "$CVE" "$DESCRIPTION" <<'PY'
import json
import re
import sys

path, new_id, name, pattern, action, category, component, cve, description = sys.argv[1:]

try:
    re.compile(pattern)
except re.error as error:
    raise SystemExit(f"push_new_signature: wzorzec nie jest poprawnym wyrazeniem regularnym: {error}")

with open(path) as handle:
    data = json.load(handle)

if any(entry.get("id") == new_id for entry in data.get("signatures", [])):
    raise SystemExit(f"push_new_signature: sygnatura o ID {new_id} juz istnieje w feedzie")

data["signatures"].append({
    "id": new_id,
    "name": name,
    "cve": cve,
    "owasp_category": category,
    "target_component": component,
    "pattern_type": "regex",
    "pattern": pattern,
    "action": action,
    "severity": "CRITICAL" if action == "block" else "INFO",
    "description": description,
})

with open(path, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY

echo "Sygnatura zapisana. Feed: http://localhost:8085/signatures.json (bez restartu kontenera)."

# Panel korzysta z kontraktu control plane (dopasowanie doslowne), wiec odswiezamy katalog tym samym
# konwerterem, ktory wywoluje `make seed`. Blad importu nie uniewaznia aktualizacji pliku.
if ! "$DIR/../scripts/import-signatures.sh"; then
  echo "Uwaga: katalog sygnatur w control plane nie zostal odswiezony (plik feedu jest aktualny)." >&2
fi
