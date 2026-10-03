#!/usr/bin/env bash
# Sprawdza, czy load balancer NAPRAWDE rozklada ruch na repliki.
#
# Sposob dzialania: kazda replika uslugi semantycznej liczy wykonane kontrole. Zapisujemy licznik
# z kazdej repliki, wysylamy zadana liczbe zadan przez load balancer (port 8001) i porownujemy
# przyrosty. Jeden kontener z calym ruchem = load balancing nie dziala.
#
# Uruchamianie: sudo make scale-check        (albo ./scripts/check-balance.sh 60)
set -euo pipefail
cd "$(dirname "$0")/.."

ZADANIA="${1:-${ZADANIA:-60}}"
SEMANTIC_URL="${SEMANTIC_URL:-http://localhost:8001}"
METRYKA="${METRYKA:-semantic_check_latency_seconds_count}"
COMPOSE="${COMPOSE:-docker compose}"

mapfile -t kontenery < <($COMPOSE ps -q semantic-app 2>/dev/null)
if [[ ${#kontenery[@]} -eq 0 ]]; then
  echo "scale-check: nie widze dzialajacych replik - uruchom: sudo make scale REPLIKI=3" >&2
  exit 1
fi
echo "scale-check: replik: ${#kontenery[@]}, zadan przez load balancer: $ZADANIA"

# Suma metryki z /metrics danej repliki (python jest w obrazie, curl/wget moze nie byc).
stan() {
  docker exec "$1" python -c "
import urllib.request
print(urllib.request.urlopen('http://localhost:8001/metrics', timeout=5).read().decode())" 2>/dev/null \
    | awk -v m="$METRYKA" -v pre="^" '$0 ~ pre m "\\{" {sum += $NF} END {printf "%d", sum + 0}'
}

przed=()
for kontener in "${kontenery[@]}"; do przed+=("$(stan "$kontener")"); done

python3 - "$SEMANTIC_URL" "$ZADANIA" <<'PY'
import json, sys, urllib.request
url, ile = sys.argv[1], int(sys.argv[2])
tekst = "Client verification: PESEL 44051401359 and card 4111111111111111."
for _ in range(ile):
    cialo = json.dumps({"text": tekst, "direction": "input",
                        "checks": ["prompt_injection", "pii_ner"], "timeout_ms": 5000}).encode()
    zadanie = urllib.request.Request(url + "/v1/scan", data=cialo,
                                     headers={"Content-Type": "application/json"})
    urllib.request.urlopen(zadanie, timeout=60).read()
PY

suma=0
przyrosty=()
for i in "${!kontenery[@]}"; do
  po="$(stan "${kontenery[$i]}")"
  delta=$((po - przed[i]))
  [[ $delta -lt 0 ]] && delta=0
  przyrosty+=("$delta")
  suma=$((suma + delta))
done

echo
for i in "${!kontenery[@]}"; do
  udzial=0
  [[ $suma -gt 0 ]] && udzial=$((przyrosty[i] * 100 / suma))
  printf '  replika %s (%s): +%s kontroli (%s%%)\n' "$((i + 1))" "${kontenery[$i]:0:12}" "${przyrosty[$i]}" "$udzial"
done
echo "  razem: +$suma kontroli"

if [[ $suma -eq 0 ]]; then
  echo "  wniosek: zadna replika nie zwiekszyla licznika - ruch nie dotarl albo metryki sa wylaczone"
  exit 1
fi

# Replika uznana za uzywana, jesli dostala choc polowe sredniego udzialu.
srednia=$((suma / ${#kontenery[@]}))
nieuzywane=0
for delta in "${przyrosty[@]}"; do
  [[ $delta -lt $((srednia / 2)) ]] && nieuzywane=$((nieuzywane + 1))
done

if [[ $nieuzywane -eq 0 ]]; then
  echo "  wniosek: ruch rozlozony na wszystkie repliki (zaden kontener nie stoi bezczynnie)"
else
  echo "  wniosek: $nieuzywane replik dostalo wyraźnie mniej ruchu - load balancing wymaga sprawdzenia"
  exit 1
fi
