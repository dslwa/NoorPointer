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
  echo "- **Gateway (Go)**: kontrole w ścieżce żądania nie są jeszcze włączone (dane osobowe, sekrety,"
  echo "  sygnatury ataków, ogranicznik pętli, budżety), brakuje \`GET /metrics\` oraz wysyłania zdarzeń"
  echo "  audytowych do \`POST /api/v1/audit/events\`. Z tego powodu 6 z 16 testów e2e nie przechodzi,"
  echo "  a pulpit gatewaya w Grafanie pozostaje pusty."
  echo "- **Kontrole semantyczne nie są w ścieżce żądania**: gateway nie wywołuje jeszcze \`/v1/scan\`."
  echo "  Osobny alert \`SemanticNoTraffic\` sygnalizuje brak ruchu do tej usługi."
  echo "- **Dwa formaty sygnatur**: feed Nginx (\`signatures-feed/signatures.json\`, wyrażenia regularne)"
  echo "  i kontrakt control plane (dopasowanie dosłowne oraz pola \`source\`/\`category\`/\`target\`) to dwa"
  echo "  różne kontrakty. Katalog w panelu zawiera reguły startowe aplikacji (migracja V2) oraz wpisy"
  echo "  z naszego feedu, dodawane pojedynczo przez \`scripts/import-signatures.sh\` (pierwsza alternatywa"
  echo "  wzorca jako wartość dosłowna); gateway jeszcze nie konsumuje sygnatur."
  echo "- **Dane audytu są demonstracyjne**: panel pokazuje wpisy utworzone przez \`make seed\`,"
  echo "  a nie rzeczywiste decyzje gatewaya."
  echo "- **Metryki gatewaya**: alert \`GatewayMetricsMissing\` (waga info) sygnalizuje brak \`/metrics\`."
  echo "  Po dodaniu endpointu trzeba odkomentować zadanie zbierające w \`telemetry/prometheus.yml\`."
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
ls -1 reports/
