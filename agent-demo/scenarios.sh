#!/usr/bin/env bash
# Advanced demo scenarios promised by agent-demo/README.md but missing from run.sh:
#   runaway-loop, unauthorized-tool, budget-exhaust.
#
# Each scenario is judged against the gateway response:
#   PASS    - blocked/limited as expected (guardrails active)
#   PENDING - request was proxied (gateway has no guardrails yet) -> turns into PASS on its own
#   FAIL    - wrong response (e.g. 401 without a JWT, 5xx, or unreachable gateway)
#
# Usage:
#   ./agent-demo/scenarios.sh                 # PENDING is allowed (pre-guardrails)
#   ./agent-demo/scenarios.sh --strict        # PENDING counts as FAIL (after gateway lands)
#   ./agent-demo/scenarios.sh runaway-loop    # single scenario
# Env: GATEWAY_URL, GATEWAY_JWT, EXHAUST_BURST
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
EXHAUST_BURST="${EXHAUST_BURST:-60}"
STRICT=0
SELECTED=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) STRICT=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) SELECTED+=("$1"); shift ;;
  esac
done

# The gateway requires an RS256 JWT on every route except /healthz. Mint one unless provided.
GATEWAY_JWT="${GATEWAY_JWT:-}"
if [[ -z "$GATEWAY_JWT" && -x scripts/token.sh ]]; then
  GATEWAY_JWT="$(./scripts/token.sh 2>/dev/null || true)"
fi
AUTH=()
[[ -n "$GATEWAY_JWT" ]] && AUTH=(-H "Authorization: Bearer $GATEWAY_JWT")

pass=0; pending=0; fail=0
CODE=000; BODY=""

request() {
  local resp
  resp=$(curl -s -m 5 -w $'\n%{http_code}' "${AUTH[@]+"${AUTH[@]}"}" "$@" 2>/dev/null) || true
  if [[ "$resp" == *$'\n'* ]]; then
    BODY="${resp%$'\n'*}"
    CODE="${resp##*$'\n'}"
  else
    BODY="$resp"; CODE="000"
  fi
  [[ "$CODE" =~ ^[0-9]{3}$ ]] || CODE="000"
}

snippet() { tr -d '\n' <<<"$BODY" | cut -c1-140; }

judge() { # judge <name> <ok_codes> <marker_regex>
  local name="$1" codes="$2" regex="$3"
  printf '\n[%s] HTTP %s\n  %s\n' "$name" "$CODE" "$(snippet)"
  if [[ ",$codes," == *",$CODE,"* ]] && grep -qE "$regex" <<<"$BODY"; then
    printf '  => PASS (guardrail active)\n'; pass=$((pass+1))
  elif [[ "$CODE" == "401" || "$CODE" == "403" && ! "$codes" == *"403"* ]]; then
    printf '  => FAIL (HTTP %s: missing/invalid JWT - run make keys && make token)\n' "$CODE"; fail=$((fail+1))
  elif [[ "$CODE" == "200" ]]; then
    printf '  => PENDING (gateway has no guardrails yet; expected %s + /%s/)\n' "$codes" "$regex"; pending=$((pending+1))
  else
    printf '  => FAIL (expected %s + /%s/)\n' "$codes" "$regex"; fail=$((fail+1))
  fi
}

scenario_runaway_loop() {
  request -H 'Content-Type: application/json' -H 'X-Tool-Call-Repeat: 3' \
    -d '{"model":"mock-llm","agent_id":"agent-runaway-loop","messages":[{"role":"user","content":"LOOP_TRIGGER_TEST repeat the same tool call again"}]}' \
    "$GATEWAY_URL/v1/chat/completions"
  judge "runaway-loop" "403,429" "RUNAWAY_LOOP|LOOP_BREAKER|LOOP_DETECTED"
}

scenario_unauthorized_tool() {
  request -H 'Content-Type: application/json' -H 'X-MCP-Tool: execute_shell' \
    -d '{"model":"mock-llm","agent_id":"agent-untrusted","messages":[{"role":"user","content":"call tool execute_shell with argument rm -rf /"}]}' \
    "$GATEWAY_URL/v1/chat/completions"
  judge "unauthorized-tool" "403" "TOOL_NOT_ALLOWED|MCP_TOOL_DENIED|UNAUTHORIZED_TOOL|TOOL_HIJACK|ALLOWLIST"
}

scenario_budget_exhaust() {
  local i
  for ((i = 1; i <= EXHAUST_BURST; i++)); do
    request -H 'Content-Type: application/json' \
      -d '{"model":"mock-llm","agent_id":"agent-budget-exhausted","messages":[{"role":"user","content":"run a large query"}]}' \
      "$GATEWAY_URL/v1/chat/completions"
    [[ "$CODE" == "200" ]] || break
  done
  judge "budget-exhaust (after ${i} requests)" "429,403" "BUDGET_EXCEEDED|RATE_LIMITED|QUOTA|TOO_MANY"
}

run() { # run <name> <fn>
  if [[ ${#SELECTED[@]} -gt 0 ]] && [[ ! " ${SELECTED[*]} " == *" $1 "* ]]; then return; fi
  "$2"
}

echo "NoorPointer advanced demo -> $GATEWAY_URL   (strict=$STRICT, jwt=$([[ -n "$GATEWAY_JWT" ]] && echo yes || echo no))"
echo "============================================================"
run runaway-loop      scenario_runaway_loop
run unauthorized-tool scenario_unauthorized_tool
run budget-exhaust    scenario_budget_exhaust

echo
echo "demo: $pass passed, $pending pending, $fail failed"
if [[ "$fail" -gt 0 ]]; then exit 1; fi
if [[ "$STRICT" -eq 1 && "$pending" -gt 0 ]]; then echo "(strict) pending scenarios count as failures"; exit 1; fi
