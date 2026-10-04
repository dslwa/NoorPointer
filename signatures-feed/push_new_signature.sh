#!/usr/bin/env bash
# PATTERN is literal text, TARGET is the canonical field (default: prompt).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/signature_feed.py add signatures-feed/signatures.json
# Surface an import failure; a saved local file alone does not activate a gateway rule.
exec ./scripts/import-signatures.sh
