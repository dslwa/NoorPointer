#!/usr/bin/env bash
# Czeka, az wszystkie uslugi odpowiadaja. Uruchamiane na koncu `make up` oraz jako `make wait`.
# Konczy sie bledem po WAIT_TIMEOUT sekundach (domyslnie 180) i wypisuje, czego brakuje.
set -uo pipefail
cd "$(dirname "$0")/.."
timeout_s="${WAIT_TIMEOUT:-180}"

# nazwa|adres|oczekiwany kod
checks=(
  "gateway|http://localhost:8080/healthz|200"
  "controlplane|http://localhost:8082/actuator/health|200"
  "mock-llm|http://localhost:11434/healthz|200"
  "feed sygnatur|http://localhost:8085/signatures.json|200"
  "prometheus|http://localhost:9091/-/ready|200"
  "grafana|http://localhost:3001/api/health|200"
  "dashboard|http://localhost:3000/|200"
  "semantic (ladowanie modeli)|http://localhost:8001/readyz|200"
)

start=$(date +%s)
while :; do
  pending=()
  for check in "${checks[@]}"; do
    IFS='|' read -r name url expected <<<"$check"
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 3 "$url" 2>/dev/null)"
    [[ "$code" == "$expected" ]] || pending+=("$name (HTTP ${code:-brak})")
  done

  if [[ "${#pending[@]}" -eq 0 ]]; then
    echo "wszystkie uslugi gotowe po $(( $(date +%s) - start )) s"
    exit 0
  fi

  if [[ $(( $(date +%s) - start )) -ge "$timeout_s" ]]; then
    echo "BRAK GOTOWOSCI po ${timeout_s} s:" >&2
    printf '  - %s\n' "${pending[@]}" >&2
    echo "sprawdz logi: sudo docker compose logs <usluga>" >&2
    exit 1
  fi

  sleep 2
done
