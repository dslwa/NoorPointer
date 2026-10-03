#!/usr/bin/env bash
# Sprawdza dzialajacy system bez przygotowan: smoke + offline-check + scenariusze demo.
# Uzycie: make verify   (--strict: scenariusze jeszcze nieobslugiwane licza sie jako blad).

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
