#!/usr/bin/env bash
# Wgrywa sygnatury z feedu (signatures-feed/signatures.json, wzorce regex) do katalogu control plane
# w kontrakcie Javy (dopasowanie doslownie) i wypisuje, ile pozycji przyjal.
#
# Uwaga na dwa formaty: gateway czyta plik z nginx (regex, pelne wzorce), a control plane ma wlasny
# kontrakt (match.type = literal, pola source/category/target). Ten skrypt nie zastepuje jednego
# formatu drugim - pokazuje ten sam zestaw sygnatur w panelu, biorac z kazdego wzorca pierwsza
# alternatywe jako wartosc doslowna. Pelna unifikacja formatow jest osobnym zadaniem.
set -euo pipefail
cd "$(dirname "$0")/.."

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
feed="signatures-feed/signatures.json"

if [[ ! -f "$feed" ]]; then
  echo "import-signatures: brak $feed" >&2
  exit 1
fi

payload="$(mktemp)"
response="$(mktemp)"
trap 'rm -f "$payload" "$response"' EXIT

python3 - "$feed" >"$payload" <<'PY'
import json
import re
import sys

with open(sys.argv[1]) as handle:
    feed = json.load(handle)

TARGETS = {
    "ray_api": "upstream_path",
    "prompt": "prompt",
    "model": "model_artifact",
    "hf": "model_artifact",
    "pickle": "model_artifact",
    "tool": "tool_name",
    "mcp": "tool_name",
    "arg": "tool_arguments",
}


def target_of(component: str) -> str:
    lowered = (component or "").lower()
    for needle, target in TARGETS.items():
        if needle in lowered:
            return target
    return "prompt"


def literal_of(pattern: str) -> str:
    """Pierwsza alternatywa wzorca bez skladni regex - wartosc dla dopasowania doslownego."""
    text = (pattern or "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    text = text.split("|")[0].replace("\\", "").strip()
    return text or (pattern or "")[:2000]


def source_of(signature: dict) -> str:
    cve = signature.get("cve", "")
    if re.fullmatch(r"CVE-\d{4}-\d{4,}", cve):
        return f"https://nvd.nist.gov/vuln/detail/{cve}"
    return "https://owasp.org/www-project-top-10-for-large-language-model-applications/"


signatures = []
for entry in feed.get("signatures", []):
    identifier = entry.get("id", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", identifier):
        continue
    description = " | ".join(
        part for part in (
            entry.get("name", ""),
            entry.get("cve", ""),
            f"wzorzec regex: {entry.get('pattern', '')}",
        ) if part
    )[:2000]
    # Jesli wpis w feedzie ma juz jawne pole match (docelowy, wspolny format), uzywamy go bez zmian;
    # w przeciwnym razie wyprowadzamy wartosc doslowna z wyrazenia regularnego.
    match = entry.get("match")
    if not (isinstance(match, dict) and match.get("type") and match.get("value")):
        match = {"type": "literal", "value": literal_of(entry.get("pattern", ""))[:2000]}
    signatures.append({
        "id": identifier,
        "name": (entry.get("name") or identifier)[:200],
        "source": entry.get("source") or source_of(entry),
        "category": (entry.get("category") or entry.get("owasp_category") or "unclassified")[:80],
        "action": "block" if entry.get("action") == "block" else "monitor",
        "target": entry.get("target") or target_of(entry.get("target_component", "")),
        "match": match,
        "description": description,
        "enabled": True,
    })

print(json.dumps({"document": json.dumps({"signatures": signatures})}))
PY

code="$(curl -s -o "$response" -w '%{http_code}' -m 10 -X PUT "$CONTROLPLANE_URL/api/v1/signature-feed" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' --data-binary @"$payload")"

case "$code" in
  200) count="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("signatures", [])))' "$response" 2>/dev/null || echo "?")"
       echo "import-signatures: control plane przyjal $count sygnatur" ;;
  401|403) echo "import-signatures: HTTP $code - sprawdz ADMIN_TOKEN ($ADMIN_TOKEN)" >&2; exit 1 ;;
  000) echo "import-signatures: brak odpowiedzi pod $CONTROLPLANE_URL - uruchom: make up" >&2; exit 1 ;;
  *)   echo "import-signatures: HTTP $code $(head -c 300 "$response")" >&2; exit 1 ;;
esac
