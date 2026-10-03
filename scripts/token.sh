#!/usr/bin/env bash
# Wystawia token JWT dla bramy i wypisuje sam token. Uruchamianie: ./scripts/token.sh
# Zmienne: AGENT, TEAM, TTL, JWT_PRIVATE_KEY. Przy bledzie konczy sie bledem - pusty token
# oznacza 401 na kazdym zadaniu, wiec nie wolno tego zignorowac.

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
