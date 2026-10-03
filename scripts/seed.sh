#!/usr/bin/env bash
# Seed demo audit data via the control plane (POST /api/v1/demo-batches).
# Needed so the audit/CEF export has rows to return. Usage: make seed
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"

body="$(curl -s -m 10 -w $'\n%{http_code}' -X POST "$CONTROLPLANE_URL/api/v1/demo-batches" \
  -H "Authorization: Bearer $ADMIN_TOKEN")"
code="${body##*$'\n'}"
payload="${body%$'\n'*}"

case "$code" in
  200|201) echo "seed: HTTP $code ${payload:0:200}" ;;
  000)     echo "seed: control plane unreachable at $CONTROLPLANE_URL - run: make up" >&2; exit 1 ;;
  401|403) echo "seed: HTTP $code - check ADMIN_TOKEN ($ADMIN_TOKEN)" >&2; exit 1 ;;
  404)     echo "seed: HTTP 404 - control plane build predates /api/v1/demo-batches; rebuild: sudo docker compose up -d --build controlplane" >&2; exit 1 ;;
  *)       echo "seed: HTTP $code $payload" >&2; exit 1 ;;
esac
