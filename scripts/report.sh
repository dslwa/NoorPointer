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
  for f in reports/test_report.html reports/smoke.txt reports/summary.html reports/summary.json; do
    if [[ -f "$f" ]]; then
      echo "- [\`$f\`]($(basename "$f"))  _(updated $(date -u -r "$f" '+%Y-%m-%dT%H:%M:%SZ'))_"
      found=1
    fi
  done
  [[ "$found" -eq 0 ]] && echo "_none yet - run: make checkpoint_"
  echo

  if [[ -f reports/smoke.txt ]]; then
    echo "## Smoke summary"
    echo
    echo '```'
    tail -1 reports/smoke.txt
    echo '```'
    echo
  fi

  echo "## Known gaps (as of $now)"
  echo
  echo "- **Gateway (Go)**: deterministic guardrails (PII/secrets/CVE/loop/budget), \`GET /metrics\`,"
  echo "  audit emission to \`POST /api/v1/audit/events\` and \`POST /admin/policy/reload\` are not implemented yet."
  echo "  This is what keeps the 7 red e2e tests red and the Grafana gateway panel empty."
  echo "- **Semantic controls are not in the request path**: the gateway does not call \`/v1/scan\` yet"
  echo "  (Prometheus alert \`SemanticNoTraffic\` tracks this)."
  echo "- **Signature formats differ**: the nginx feed (\`signatures-feed/signatures.json\`, regex patterns,"
  echo "  gateway \`SIGNATURES_FEED_URL\`) and the control-plane schema (\`match.type: literal\` +"
  echo "  \`source/category/target\`) are not the same contract - unification pending."
  echo "- **Audit data is synthetic**: the dashboard shows demo batches created by \`make seed\`,"
  echo "  not live gateway decisions, until audit emission lands."
  echo "- **Gateway metrics**: \`GatewayMetricsMissing\` (info) is the explicit \"we don't know\" badge for"
  echo "  the missing \`/metrics\` endpoint; re-enable the scrape job in \`telemetry/prometheus.yml\` with it."
  echo

  echo "## Reproduce"
  echo
  echo '```bash'
  echo "sudo make keys        # once per machine (gitignored keypair)"
  echo "sudo make up          # full stack + demo seed (mock LLM upstream, offline at runtime)"
  echo "make smoke            # 16 wiring checks"
  echo "sudo make test        # pytest e2e -> reports/test_report.html"
  echo "sudo make bench       # k6 baseline (p95)"
  echo "sudo make bench-flood # k6 malicious flood"
  echo "sudo make demo-full    # 8 demo scenarios"
  echo "sudo make checkpoint  # everything above, one shot"
  echo '```'
} > reports/INDEX.md

echo "wrote reports/INDEX.md"
ls -1 reports/
