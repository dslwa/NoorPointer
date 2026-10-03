#!/usr/bin/env bash
# Mint a gateway JWT (RS256, iss=noorpointer-cp, aud=noorpointer-gateway). Prints only the token.
# Usage: ./scripts/token.sh   (env: AGENT, TEAM, TTL, JWT_PRIVATE_KEY)
#
# Fails LOUDLY: an empty token makes every gateway call return 401, and in a Makefile
# $(...) an empty result looks like a normal value - that is exactly how a token problem
# once looked like 13 broken auth tests.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo/gateway"

key="${JWT_PRIVATE_KEY:-keys/jwt.key}"
if [[ ! -f "$key" ]]; then
  echo "token: missing $key - run: make keys" >&2
  exit 1
fi

# Prefer the prebuilt binary: no toolchain, no module downloads, works under sudo/env_reset.
if [[ -x bin/mint ]]; then
  exec ./bin/mint
fi

go_bin="$(command -v go || true)"
if [[ -z "$go_bin" ]]; then
  echo "token: no go toolchain and no gateway/bin/mint - run 'make mint-build' as your user" >&2
  exit 1
fi

# Redirect go caches somewhere writable (root under sudo may have no HOME/.cache).
export GOCACHE="${GOCACHE:-${TMPDIR:-/tmp}/noorpointer-go-build}"
export GOMODCACHE="${GOMODCACHE:-${TMPDIR:-/tmp}/noorpointer-go-mod}"
mkdir -p "$GOCACHE" "$GOMODCACHE"

token="$("$go_bin" run ./cmd/mint)"
if [[ -z "$token" ]]; then
  echo "token: mint produced no output" >&2
  exit 1
fi
printf '%s\n' "$token"
