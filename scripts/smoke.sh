#!/usr/bin/env bash
# Zero-prep smoke check of the whole stack. Usage: make smoke
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
SEMANTIC_URL="${SEMANTIC_URL:-http://localhost:8001}"
CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}"
MOCK_LLM_URL="${MOCK_LLM_URL:-http://localhost:11434}"
FEED_URL="${FEED_URL:-http://localhost:8085/signatures.json}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9091}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"

# The gateway requires an RS256 JWT on every route except /healthz. Mint one unless provided.
GATEWAY_JWT="${GATEWAY_JWT:-}"
if [[ -z "$GATEWAY_JWT" && -x scripts/token.sh ]]; then
  GATEWAY_JWT="$(./scripts/token.sh 2>/dev/null || true)"
fi
AUTH=()
[[ -n "$GATEWAY_JWT" ]] && AUTH=(-H "Authorization: Bearer $GATEWAY_JWT")

pass=0; fail=0
ok()   { printf '  PASS  %-26s %s\n' "$1" "$2"; pass=$((pass+1)); }
bad()  { printf '  FAIL  %-26s %s\n' "$1" "$2"; fail=$((fail+1)); }

# check_code <name> <expected|a,b> <url> [curl args...]
check_code() {
  local name="$1" expected="$2" url="$3"; shift 3
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$@" "$url" 2>/dev/null)
  if [[ ",$expected," == *",$code,"* ]]; then ok "$name" "$code"; else bad "$name" "got=${code:-000} want=$expected"; fi
}

# check_body <name> <url> <needle> [curl args...]
check_body() {
  local name="$1" url="$2" needle="$3"; shift 3
  local body
  body=$(curl -s --max-time 6 "$@" "$url" 2>/dev/null)
  if grep -q "$needle" <<<"$body"; then ok "$name" "contains '$needle'"; else bad "$name" "missing '$needle'"; fi
}

echo "== health endpoints =="
check_code "gateway /healthz"     200 "$GATEWAY_URL/healthz"
check_code "semantic /healthz"    200 "$SEMANTIC_URL/healthz"
check_code "controlplane health"  200 "$CONTROLPLANE_URL/actuator/health"
check_code "dashboard /"          200 "$DASHBOARD_URL/"
check_code "mock-llm /healthz"    200 "$MOCK_LLM_URL/healthz"
check_code "signatures feed"      200 "$FEED_URL"
check_code "prometheus ready"     200 "$PROMETHEUS_URL/-/ready"
check_code "grafana health"       200 "$GRAFANA_URL/api/health"
# 200 = ready, 503 = still loading models (informational, does not fail the run)
check_code "semantic /readyz"     "200,503" "$SEMANTIC_URL/readyz"

echo "== proxy + guardrail wiring =="
# Authenticated proxy call. A 401 here means the gateway rejects a token we believe is valid -
# almost always a stale in-memory jwt.pub (the gateway reads the key only at startup).
gw_out="$(mktemp)"
gw_code=$(curl -s -o "$gw_out" -w '%{http_code}' --max-time 6 "${AUTH[@]+"${AUTH[@]}"}" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"model":"mock-llm","agent_id":"smoke","messages":[{"role":"user","content":"smoke test"}]}' \
  "$GATEWAY_URL/v1/chat/completions" 2>/dev/null)
if [[ "$gw_code" == "200" ]] && grep -q choices "$gw_out"; then
  ok "gateway -> mock-llm" "contains 'choices'"
else
  bad "gateway -> mock-llm" "got=${gw_code:-000}"
  if [[ "$gw_code" == "401" || "$gw_code" == "403" ]]; then
    echo "        HINT: gateway rejects the minted token. It reads jwt.pub only at startup, so a"
    echo "              regenerated keypair needs: sudo docker compose up -d --force-recreate gateway"
    [[ -n "$GATEWAY_JWT" ]] && ./scripts/verify-token-sig.sh "$GATEWAY_JWT" 2>&1 | sed 's/^/        /'
  fi
fi
rm -f "$gw_out"
# 200 = JWT not enforced yet, 401/403 = auth active (both are healthy outcomes here)
check_code "gateway auth enforced?" "200,401,403" "$GATEWAY_URL/v1/chat/completions" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"model":"mock-llm","messages":[{"role":"user","content":"no token"}]}'
check_body "mock-llm guard /api/chat" "$MOCK_LLM_URL/api/chat" "safe" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"nice weather"}]}'
check_body "signatures payload" "$FEED_URL" "signatures"
check_body "semantic /v1/scan" "$SEMANTIC_URL/v1/scan" "flagged" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"text":"hello","checks":["prompt_injection"],"timeout_ms":1000}'

echo "== control plane auth =="
check_code "audit export (no token)" "401,403" "$CONTROLPLANE_URL/api/v1/audit/export?format=cef"
check_code "audit export (admin)"    200 "$CONTROLPLANE_URL/api/v1/audit/export?format=cef" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

echo
[[ -z "$GATEWAY_JWT" ]] && echo "note: no gateway JWT - run 'make keys' then retry (scripts/token.sh mints one)"
echo "smoke: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
