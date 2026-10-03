#!/usr/bin/env bash
# Sprawdza podpis tokenu JWT kluczem gateway/keys/jwt.pub.
# Uzycie: verify-token-sig.sh <token>

set -euo pipefail
tok="$1"
pub="${2:-$(cd "$(dirname "$0")/.." && pwd)/gateway/keys/jwt.pub}"

data="${tok%.*}"
sig_b64="${tok##*.}"

python3 -c "
import base64, sys
s = sys.argv[1]
s += '=' * (-len(s) % 4)
open('/tmp/jwt.sig', 'wb').write(base64.urlsafe_b64decode(s))
" "$sig_b64"

printf '%s' "$data" > /tmp/jwt.signed

if openssl dgst -sha256 -verify "$pub" -signature /tmp/jwt.sig /tmp/jwt.signed >/dev/null 2>&1; then
  echo "signature VALID against $(basename "$pub")"
else
  echo "signature INVALID against $(basename "$pub")" >&2
  exit 1
fi
