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

# Import po stronie control plane nie jest jeszcze podlaczony: obecny kontrakt wymaga innego
# formatu sygnatur, a ten endpoint nie istnieje. Raportujemy kod odpowiedzi, zeby nie bylo
# watpliwosci, czy import sie powiodl.
code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST "$CONTROLPLANE_URL/api/v1/signatures/sync" || true)"
case "${code:-000}" in
  200|201|204) echo "Control plane: HTTP $code (import wykonany)." ;;
  000)         echo "Control plane: brak odpowiedzi pod $CONTROLPLANE_URL." ;;
  401|403)     echo "Control plane: HTTP $code - endpoint wymaga tokenu administratora, a import tego formatu nie jest podlaczony (patrz README)." ;;
esac
