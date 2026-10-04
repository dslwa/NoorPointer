#!/usr/bin/env bash
# Run independently testable changes. No Go build, deployment or policy publication.
set -euo pipefail
cd "$(dirname "$0")/.."
test_python="${TEST_PYTHON:-$PWD/semantic-service/.venv/bin/python}"
if [[ ! -x "$test_python" ]]; then
  echo "Brak venv. Uruchom: cd semantic-service && uv sync" >&2
  exit 1
fi
if [[ "$test_python" != /* ]]; then
  test_python="$PWD/$test_python"
fi
(cd semantic-service && "$test_python" -m pytest -q)
"$test_python" -m pytest tests/test_signature_feed.py -q
(cd controlplane && mvn -B -ntp -Dfrontend.skip=true -Dtest=PolicyTypesTest test)
(cd dashboard && npm test -- --run && npm run build)
