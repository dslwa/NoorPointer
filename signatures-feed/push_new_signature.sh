#!/usr/bin/env bash
# Dodaje nowa sygnature do feedu, zeby pokazac aktualizacje reguly bez restartu kontenera.
# Uruchamianie: ./signatures-feed/push_new_signature.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIG_FILE="$DIR/signatures.json"
CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"

NEW_ID="SIG-$(date +%Y%m%d-%H%M%S)"
echo "Dodawanie sygnatury $NEW_ID do feedu."

python3 - "$SIG_FILE" "$NEW_ID" <<'PY'
import json
import sys

path, new_id = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)

data['signatures'].append({
    'id': new_id,
    'name': 'Zero-Day Live Injected Attack Pattern',
    'cve': 'CVE-LIVE-EMERGENCY',
    'owasp_category': 'LLM01: Prompt Injection',
    'target_component': 'prompt_filter',
    'pattern_type': 'regex',
    'pattern': 'HACKATHON_ZERO_DAY_PAYLOAD_TEST',
    'action': 'block',
    'severity': 'CRITICAL',
    'description': 'Dynamicznie dodana regula podczas prezentacji dla jury.',
})

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
PY

echo "Sygnatura zapisana. Feed: http://localhost:8085/signatures.json (bez restartu kontenera)."

# Panel korzysta z kontraktu control plane (dopasowanie doslowne), wiec odswiezamy katalog tym samym
# konwerterem, ktory wywoluje `make seed`. Blad importu nie uniewaznia aktualizacji pliku.
if ! "$DIR/../scripts/import-signatures.sh"; then
  echo "Uwaga: katalog sygnatur w control plane nie zostal odswiezony (plik feedu jest aktualny)." >&2
fi
