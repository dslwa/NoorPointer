#!/usr/bin/env bash
# Seed demo audit data via the control plane (POST /api/v1/demo-batches).
# Needed so the audit/CEF export and the SOC dashboard have rows. Usage: make seed
# Retries while the control plane is still starting (docker compose up -d returns before it is ready).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
ATTEMPTS="${SEED_RETRIES:-15}"
DELAY="${SEED_DELAY:-2}"

fail() { echo "seed: $1" >&2; exit 1; }

for i in $(seq 1 "$ATTEMPTS"); do
  body="$(curl -s -m 10 -w $'\n%{http_code}' -X POST "$CONTROLPLANE_URL/api/v1/demo-batches" \
    -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null)" || true
  code="${body##*$'\n'}"
  payload="${body%$'\n'*}"

  case "${code:-000}" in
    200|201) echo "seed: HTTP $code ${payload:0:200}"; exit 0 ;;
    000|502|503|504)
      if [[ "$i" -eq "$ATTEMPTS" ]]; then
        fail "control plane not ready at $CONTROLPLANE_URL after $ATTEMPTS attempts - run: make up"
      fi
      sleep "$DELAY"
      ;;
    401|403) fail "HTTP $code - check ADMIN_TOKEN ($ADMIN_TOKEN)" ;;
    404)     fail "HTTP 404 - control plane build predates /api/v1/demo-batches; rebuild: sudo docker compose up -d --build controlplane" ;;
    *)       fail "HTTP $code $payload" ;;
  esac
done
