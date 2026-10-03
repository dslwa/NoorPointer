#!/usr/bin/env bash
# Wypelnia control plane danymi demonstracyjnymi: zdarzenia audytu (POST /api/v1/demo-batches)
# oraz katalog sygnatur z feedu. Uruchamianie: make seed (wywolywane tez przez make up i make test).
# Powtarza probe, dopoki control plane nie wstanie (docker compose up konczy sie przed gotowoscia).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
ATTEMPTS="${SEED_RETRIES:-15}"
DELAY="${SEED_DELAY:-2}"

fail() { echo "seed: $1" >&2; exit 1; }

for i in $(seq 1 "$ATTEMPTS"); do
  body="$(curl -s -m 10 -w $'\n%{http_code}' -X POST "$CONTROLPLANE_URL/api/v1/demo-batches" \
    -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null)" || true
  code="${body##*$'\n'}"
  payload="${body%$'\n'*}"

  case "${code:-000}" in
    200|201)
      echo "seed: zdarzenia audytu, HTTP $code ${payload:0:180}"
      # Katalog sygnatur jest niezalezny od audytu, wiec jego blad nie przerywa seeda.
      ./scripts/import-signatures.sh || echo "seed: import sygnatur nie powiodl sie (patrz komunikat wyzej)" >&2
      exit 0
      ;;
    000|502|503|504)
      if [[ "$i" -eq "$ATTEMPTS" ]]; then
        fail "control plane nie odpowiada pod $CONTROLPLANE_URL po $ATTEMPTS probach - uruchom: make up"
      fi
      sleep "$DELAY"
      ;;
    401|403) fail "HTTP $code - sprawdz ADMIN_TOKEN ($ADMIN_TOKEN)" ;;
    404)     fail "HTTP 404 - obraz control plane nie ma /api/v1/demo-batches; przebuduj: sudo docker compose up -d --build controlplane" ;;
    *)       fail "HTTP $code $payload" ;;
  esac
done
