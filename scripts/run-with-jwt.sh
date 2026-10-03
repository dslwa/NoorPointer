#!/usr/bin/env bash
# Run a command with a freshly minted gateway JWT exported as GATEWAY_JWT.
# Usage: ./scripts/run-with-jwt.sh <command...>
# Aborts loudly if the token cannot be minted, instead of silently sending "Bearer " (401).
set -euo pipefail
cd "$(dirname "$0")/.."

jwt="$(./scripts/token.sh)"
if [[ -z "$jwt" ]]; then
  echo "run-with-jwt: empty token - run 'make keys && make mint-build'" >&2
  exit 1
fi

export GATEWAY_JWT="$jwt"
exec "$@"
