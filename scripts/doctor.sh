#!/usr/bin/env bash
# Pre-flight / troubleshooting check. Usage: make doctor
# Verifies tooling, JWT keys (and the docker bind-mount footgun), compose config, token minting and
# whether the running gateway actually enforces auth. Never touches the stack.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

pass=0; warn=0; fail=0
ok(){ printf '  OK    %-32s %s\n' "$1" "$2"; pass=$((pass+1)); }
wn(){ printf '  WARN  %-32s %s\n' "$1" "$2"; warn=$((warn+1)); }
no(){ printf '  FAIL  %-32s %s\n' "$1" "$2"; fail=$((fail+1)); }

echo "== tooling =="
command -v docker  >/dev/null && ok "docker"  "$(docker --version 2>/dev/null | cut -d, -f1)" || no "docker" "not found"
command -v go      >/dev/null && ok "go"      "$(go version 2>/dev/null | awk '{print $3}')" || wn "go" "not found - scripts/token.sh needs it"
command -v openssl >/dev/null && ok "openssl" "$(openssl version 2>/dev/null | awk '{print $1, $2}')" || wn "openssl" "not found - make keys needs it"

echo "== JWT keys =="
for f in gateway/keys/jwt.key gateway/keys/jwt.pub; do
  if   [[ -f "$f" ]]; then ok "$f" "regular file"
  elif [[ -d "$f" ]]; then no "$f" "DIRECTORY (docker bind-mount footgun): rm -rf $f && make keys"
  else                     no "$f" "missing - run: make keys"
  fi
done

echo "== compose =="
if docker compose config --quiet 2>/dev/null; then ok "docker compose config" "valid"; else no "docker compose config" "invalid - run: docker compose config"; fi

echo "== token =="
if [[ -f gateway/keys/jwt.key ]] && command -v go >/dev/null; then
  tok="$(./scripts/token.sh 2>/dev/null || true)"
  if [[ -n "$tok" ]]; then
    payload="$(cut -d. -f2 <<<"$tok" | sed 's/-/+/g; s/_/\//g')"
    pad=$(( (4 - ${#payload} % 4) % 4 ))
    [[ $pad -gt 0 ]] && payload+="$(printf '=%.0s' $(seq 1 $pad))"
    claims="$(printf '%s' "$payload" | base64 -d 2>/dev/null || true)"
    if [[ -n "$claims" ]]; then
      ok "token minted" "$(sed -nE 's/.*"iss":"([^"]+)".*/iss=\1/p; s/.*"sub":"([^"]+)".*/sub=\1/p' <<<"$claims" | tr '\n' ' ')"
    else
      wn "token minted" "minted but claims not decodable"
    fi
  else
    no "token minted" "scripts/token.sh failed"
  fi
else
  wn "token minted" "skipped (no jwt.key or go)"
fi

echo "== running gateway =="
code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{"model":"mock-llm","messages":[]}' 2>/dev/null)"
case "${code:-000}" in
  401|403) ok "auth enforced (no token)" "$code" ;;
  000)     wn "gateway reachable" "not running: sudo docker compose up -d gateway" ;;
  200)     wn "auth enforced (no token)" "200 - running build predates JWT; rebuild: sudo docker compose up -d --build gateway" ;;
  *)       wn "auth enforced (no token)" "unexpected $code" ;;
esac

echo
echo "doctor: $pass ok, $warn warn, $fail fail"
[[ "$fail" -eq 0 ]]
