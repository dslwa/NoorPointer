#!/usr/bin/env bash
# Collect evidence for the jury into reports/INDEX.md. Usage: make report
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports

commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

{
  echo "# NoorPointer - evaluation evidence"
  echo
  echo "- generated: $now"
  echo "- commit: \`$commit\`"
  echo
  echo "## Artifacts"
  echo
  found=0
  for f in reports/test_report.html reports/summary.html reports/summary.json reports/smoke.txt; do
    if [[ -f "$f" ]]; then
      echo "- [\`$f\`]($(basename "$f"))"; found=1
    fi
  done
  [[ "$found" -eq 0 ]] && echo "_none yet - run: make test, make bench, make smoke | tee reports/smoke.txt_"
  echo
  echo "## Reproduce"
  echo
  echo '```bash'
  echo "sudo make up        # full stack (mock LLM upstream, no internet needed at runtime)"
  echo "sudo make test      # pytest e2e suite -> reports/test_report.html"
  echo "sudo make bench     # k6 baseline  -> p95 latency"
  echo "sudo make smoke     # wiring check of every service"
  echo "sudo make offline-check"
  echo '```'
} > reports/INDEX.md

echo "wrote reports/INDEX.md"
ls -1 reports/
