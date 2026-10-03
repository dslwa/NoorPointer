#!/usr/bin/env bash
# Zero-prep verification of the running stack: smoke + offline-check + demo scenarios.
# Usage: ./scripts/verify.sh [--strict]
#   --strict   treat PENDING scenarios (controls the gateway does not implement yet) as failures
# Aggregates exit codes, so a failing smoke run is not masked by a passing last command.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports

strict=""
[[ "${1:-}" == "--strict" ]] && strict="--strict"

rc=0

echo "### smoke -> reports/smoke.txt"
./scripts/smoke.sh | tee reports/smoke.txt || rc=1

echo
echo "### offline-check"
./scripts/offline-check.sh || rc=1

echo
echo "### demo scenarios${strict:+ (strict)}"
./agent-demo/scenarios.sh $strict || rc=1

echo
if [[ "$rc" -eq 0 ]]; then
  echo "verify: OK"
else
  echo "verify: FAILED (zobacz sekcje wyzej; PENDING w trybie nie-strict nie jest bledem)"
fi
exit "$rc"
