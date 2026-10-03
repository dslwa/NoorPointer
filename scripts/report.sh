#!/usr/bin/env bash
# Zbiera dowody dla osob oceniajacych do reports/INDEX.md. Uruchamianie: make report
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports

commit=$(git rev-parse --short HEAD 2>/dev/null || echo "brak")
now=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

{
  echo "# NoorPointer — dowody dla oceniających"
  echo
  echo "- wygenerowano: $now"
  echo "- commit: \`$commit\`"
  echo

  echo "## Pliki wynikowe"
  echo
  found=0
  for f in reports/test_report.html reports/smoke.txt reports/summary.html reports/summary.json; do
    if [[ -f "$f" ]]; then
      echo "- [\`$f\`]($(basename "$f")) — zmieniony $(date -u -r "$f" '+%Y-%m-%dT%H:%M:%SZ')"
      found=1
    fi
  done
  [[ "$found" -eq 0 ]] && echo "_brak plików — uruchom: make checkpoint_"
  echo

  if [[ -f reports/smoke.txt ]]; then
    echo "## Wynik sprawdzenia spójności (smoke)"
    echo
    echo '```'
    tail -1 reports/smoke.txt
    echo '```'
    echo
  fi

  echo "## Znane luki (stan na $now)"
  echo
  echo "- **Brama egzekwuje część kontroli**: działają allowlista modeli, sekrety, redakcja danych osobowych"
  echo "  oraz kontrole semantyczne (prompt injection, content safety) przez gRPC. Otwarte pozostają:"
  echo "  sygnatury ataków, budżety, ogranicznik pętli i lista narzędzi MCP."
  echo "- **Brak \`GET /metrics\` w bramie** (port 9090). Alert \`GatewayMetricsMissing\` (waga info) to"
  echo "  sygnalizuje; po dodaniu endpointu odkomentuj zadanie zbierające w \`telemetry/prometheus.yml\`."
  echo "- **Brama nie wysyła zdarzeń audytowych** do \`POST /api/v1/audit/events\` — dziennik w panelu"
  echo "  zasilają dane demonstracyjne z \`make seed\` (oznaczone jako \`synthetic\`)."
  echo "- **PII w wolnym tekście i wyciek systemowego promptu** (\`pii_ner\`, \`leakage\`) działają w usłudze"
  echo "  semantycznej, ale brama woła na razie tylko prompt injection i content safety."
  echo "- **Dwa formaty sygnatur**: feed Nginx (regex) i kontrakt control plane (dopasowanie dosłowne +"
  echo "  pola \`source\`/\`category\`/\`target\`) to dwa różne kontrakty; gateway nie konsumuje sygnatur."
  echo "- **Testy e2e**: \`tests/test_guardrails.py\` ma 25 przypadków; pełny wynik tego przebiegu jest"
  echo "  w raporcie HTML z \`sudo make test\` (PENDING = kontroli jeszcze nie ma, FAIL = kontrola nie działa)."
  echo

  echo "## Jak to odtworzyć"
  echo
  echo '```bash'
  echo "sudo make keys        # raz na maszynie (klucze nie są wersjonowane)"
  echo "sudo make up          # cały stos + dane demonstracyjne (upstream: mock-llm, bez dostępu do sieci)"
  echo "make smoke            # 16 sprawdzeń spójności stosu"
  echo "sudo make test        # testy e2e -> reports/test_report.html"
  echo "sudo make bench       # k6: narzut przy typowym ruchu"
  echo "sudo make bench-flood # k6: duży ruch z próbami ataku"
  echo "sudo make demo-full   # scenariusze demonstracyjne"
  echo "sudo make checkpoint  # wszystko powyżej jednym poleceniem"
  echo '```'
} > reports/INDEX.md

echo "zapisano reports/INDEX.md"
# Po przebiegu pod sudo raport zostaje root-owned - przywroc wlasciciela repo (jak w make test).
chown -R "$(stat -c '%u:%g' .)" reports 2>/dev/null || true
ls -1 reports/
