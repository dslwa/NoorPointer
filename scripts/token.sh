#!/usr/bin/env bash
# Mint a gateway JWT (RS256, iss=noorpointer-cp, aud=noorpointer-gateway). Prints only the token.
# Usage: ./scripts/token.sh
# Env passthrough: AGENT (sub), TEAM, TTL (e.g. 24h), JWT_PRIVATE_KEY
set -euo pipefail
cd "$(dirname "$0")/../gateway"

if [[ ! -f "${JWT_PRIVATE_KEY:-keys/jwt.key}" ]]; then
  echo "missing gateway/keys/jwt.key - run: make keys" >&2
  exit 1
fi
exec go run ./cmd/mint
