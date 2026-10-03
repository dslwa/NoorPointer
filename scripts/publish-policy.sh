#!/usr/bin/env bash
# Ustawia zasady demo w control plane: dopisuje modele uzywane w testach i demo oraz jeden wpis
# budzetowy. Powtarzalne - jesli to juz jest, nie tworzy nowej wersji.

set -euo pipefail
cd "$(dirname "$0")/.."

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
required_models=("mock-llm" "llama3.2:1b")
budget_fixture="agent:agent-budget-exhausted"

auth=(-H "Authorization: Bearer $ADMIN_TOKEN")
active="$(mktemp)"; draft="$(mktemp)"; response="$(mktemp)"
trap 'rm -f "$active" "$draft" "$response"' EXIT

code="$(curl -s -o "$active" -w '%{http_code}' -m 10 "$CONTROLPLANE_URL/api/v1/active-policy" "${auth[@]}")"
case "$code" in
  200) ;;
  000) echo "publish-policy: brak odpowiedzi pod $CONTROLPLANE_URL - uruchom: make up" >&2; exit 1 ;;
  401|403) echo "publish-policy: HTTP $code - sprawdz ADMIN_TOKEN" >&2; exit 1 ;;
  *) echo "publish-policy: HTTP $code przy odczycie aktywnej polityki" >&2; exit 1 ;;
esac

python3 - "$active" "$draft" "${required_models[@]}" "$budget_fixture" <<'PY'
import json
import sys

source, target, *rest = sys.argv[1:]
models_wanted, budget_subject = rest[:-1], rest[-1]

with open(source) as handle:
    document = json.load(handle)["revision"]["document"]

document.pop("version", None)
document.setdefault("models", {}).setdefault("allowed", [])
document["models"]["allowed"] = sorted(set(document["models"]["allowed"]) | set(models_wanted))

budgets = document.setdefault("budgets", [])
if not any(entry.get("subject") == budget_subject for entry in budgets):
    # daily_tokens 0 oznacza budzet przekroczony od pierwszego zadania - deterministyczny
    # przypadek testowy, ktory nie zalezy od stanu licznikow.
    budgets.append({"subject": budget_subject, "daily_tokens": 0, "on_exceed": "block"})

with open(target, "w") as handle:
    json.dump(
        {
            "name": "balanced-demo",
            "description": (
                "Profil balanced + modele uzywane w testach, benchmarkach i demo "
                "(mock-llm, llama3.2:1b) oraz deterministyczny wpis budzetowy "
                f"({budget_subject}, daily_tokens 0)."
            ),
            "document": json.dumps(document),
        },
        handle,
    )
PY

current="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]))["revision"]["document"];d.pop("version",None);print(json.dumps(d,sort_keys=True))' "$active")"
wanted="$(python3 -c 'import json,sys;print(json.dumps(json.loads(json.load(open(sys.argv[1]))["document"]),sort_keys=True))' "$draft")"

if [[ "$current" == "$wanted" ]]; then
  echo "publish-policy: aktywna polityka juz zawiera wymagane modele i wpis budzetowy - bez zmian"
  exit 0
fi

code="$(curl -s -o "$response" -w '%{http_code}' -m 10 -X POST "$CONTROLPLANE_URL/api/v1/policy-revisions" \
  "${auth[@]}" -H 'Content-Type: application/json' --data-binary @"$draft")"
if [[ "$code" != "201" ]]; then
  echo "publish-policy: HTTP $code przy tworzeniu rewizji: $(head -c 300 "$response")" >&2
  exit 1
fi
version="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print((d.get("revision") or d)["version"])' "$response")"

code="$(curl -s -o "$response" -w '%{http_code}' -m 10 -X PUT "$CONTROLPLANE_URL/api/v1/active-policy" \
  "${auth[@]}" -H 'Content-Type: application/json' -d "{\"version\": $version}")"
if [[ "$code" != "200" ]]; then
  echo "publish-policy: HTTP $code przy aktywacji rewizji $version: $(head -c 300 "$response")" >&2
  exit 1
fi

[[ "${QUIET:-0}" == "1" ]] || echo "publish-policy: aktywna rewizja $version (models.allowed: ${required_models[*]}, budzet: $budget_fixture)"
