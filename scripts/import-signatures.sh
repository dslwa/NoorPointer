#!/usr/bin/env bash
# Additive import of canonical literal rules. Conflicts fail; nothing is silently converted or replaced.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/signature_feed.py import \
  controlplane/src/main/resources/signatures/defaults.json signatures-feed/signatures.json
