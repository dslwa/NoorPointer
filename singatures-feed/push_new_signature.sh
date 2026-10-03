#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIG_FILE="$DIR/signatures.json"

NEW_ID="SIG-$(date +%Y%m%d-%H%M%S)"
echo "🚀 Adding live zero-day signature [$NEW_ID] to feed..."

# Append new signature to signatures.json using python helper
python3 -c "
import json
with open('$SIG_FILE', 'r') as f:
    data = json.load(f)

new_sig = {
    'id': '$NEW_ID',
    'name': 'Zero-Day Live Injected Attack Pattern',
    'cve': 'CVE-LIVE-EMERGENCY',
    'owasp_category': 'LLM01: Prompt Injection',
    'target_component': 'prompt_filter',
    'pattern_type': 'regex',
    'pattern': 'HACKATHON_ZERO_DAY_PAYLOAD_TEST',
    'action': 'block',
    'severity': 'CRITICAL',
    'description': 'Dynamicznie dodana reguła podczas prezentacji dla jury.'
}

data['signatures'].append(new_sig)
with open('$SIG_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"

echo "✅ Signature added to feed. Triggering Control Plane / Gateway sync..."
curl -s -X POST "http://localhost:8082/api/v1/signatures/sync" || echo "Note: Control Plane not responding yet, signature available at feed:8085."
echo "🎉 Done! New attack signature is now live."
