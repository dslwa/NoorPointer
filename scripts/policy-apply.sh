#!/usr/bin/env bash
# Publikuje edytowana polityke jako nowa rewizje, aktywuje ja i kaze gatewayowi przeladowac
# konfiguracje. Nie restartuje zadnego kontenera.
#
# Uzycie: make policy-apply        (domyslnie plik policy.local.json, NAME= nazwa rewizji)
set -euo pipefail
cd "$(dirname "$0")/.."

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
GATEWAY_TOKEN="${GATEWAY_TOKEN:-local-dev-gateway}"
FILE="${FILE:-policy.local.json}"
NAME="${NAME:-jury-$(date +%H%M%S)}"

if [[ ! -f "$FILE" ]]; then
  echo "policy-apply: brak pliku $FILE - najpierw uruchom: make policy-edit" >&2
  exit 1
fi

python3 - "$FILE" "$NAME" "$CONTROLPLANE_URL" "$ADMIN_TOKEN" "$GATEWAY_URL" "$GATEWAY_TOKEN" <<'PY'
import json
import sys
import urllib.error
import urllib.request

path, name, cp_url, admin_token, gateway_url, gateway_token = sys.argv[1:7]

try:
    with open(path) as handle:
        document = json.load(handle)
except json.JSONDecodeError as error:
    raise SystemExit(f"policy-apply: {path} nie jest poprawnym JSON-em: {error}")


def call(method, url, token, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:300]
    except urllib.error.URLError as error:
        raise SystemExit(f"policy-apply: {url} nie odpowiada ({error}). Uruchom najpierw: make up")


status, body = call(
    "POST",
    f"{cp_url}/api/v1/policy-revisions",
    admin_token,
    {"name": name, "document": json.dumps(document)},
)
if status not in (200, 201):
    raise SystemExit(f"policy-apply: utworzenie rewizji zwrocilo HTTP {status}: {body}")
version = (body.get("revision") or body)["version"]
print(f"policy-apply: powstala rewizja {version} o nazwie {name}")

status, body = call("PUT", f"{cp_url}/api/v1/active-policy", admin_token, {"version": version})
if status != 200:
    raise SystemExit(f"policy-apply: aktywacja rewizji {version} zwrocila HTTP {status}: {body}")
print(f"policy-apply: rewizja {version} jest teraz aktywna")

status, body = call("POST", f"{gateway_url}/admin/policy/reload", gateway_token)
print(f"policy-apply: gateway przeladowal polityke -> HTTP {status} {body}")
if status != 200:
    raise SystemExit("policy-apply: gateway nie potwierdzil przeladowania")
PY
