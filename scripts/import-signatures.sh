#!/usr/bin/env bash
# Uzupelnia katalog sygnatur w control plane. NICZEGO nie kasuje: wpisy dodane z panelu, wpisy
# domyslne aplikacji i wpisy z feedu wspolistnieja, a powtorne uruchomienie konczy sie na "juz bylo".
#
# Zrodla (w tej kolejnosci):
#   1. controlplane/src/main/resources/signatures/defaults.json - wbudowane reguly startowe aplikacji
#      (ten sam plik czyta migracja V2; importujemy je takze tutaj, zeby katalog byl spojny wtedy,
#      gdy migracja juz przebiegla, a wpisy zostaly skasowane);
#   2. signatures-feed/signatures.json - nasz feed dla gatewaya (wzorce regex).
#
# Uwaga na dwa formaty: gateway czyta plik z nginx (regex, pelne wzorce), a control plane ma wlasny
# kontrakt (match.type = literal, pola source/category/target). Ten skrypt nie zastepuje jednego
# formatu drugim - pokazuje ten sam zestaw sygnatur w panelu, biorac z kazdego wzorca pierwsza
# alternatywe jako wartosc doslowna. Pelna unifikacja formatow jest osobnym zadaniem.
#
# Endpoint: POST /api/v1/signatures (pojedynczy wpis, 409 = taki ID juz istnieje).
# Nie uzywamy PUT /api/v1/signature-feed, bo on podmienia CALY katalog i kasuje wpisy dodane z panelu.
set -euo pipefail
cd "$(dirname "$0")/.."

CONTROLPLANE_URL="${CONTROLPLANE_URL:-http://localhost:8082}"
ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}"
sources=(
  "controlplane/src/main/resources/signatures/defaults.json"
  "signatures-feed/signatures.json"
)

payload="$(mktemp)"
response="$(mktemp)"
trap 'rm -f "$payload" "$response"' EXIT

for source in "${sources[@]}"; do
  if [[ ! -f "$source" ]]; then
    echo "import-signatures: pomijam brakujacy $source" >&2
    continue
  fi
  python3 - "$source" <<'PY' >>"$payload"
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


for entry in feed.get("signatures", []):
    identifier = entry.get("id", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", identifier):
        continue
    # Wpisy zgodne z kontraktem control plane (np. wbudowane defaults) przechodza bez zmian;
    # wpisom z feedu dopisujemy brakujace pola, wyprowadzajac wartosc doslowna z wyrazenia regularnego.
    match = entry.get("match")
    if not (isinstance(match, dict) and match.get("type") and match.get("value")):
        match = {"type": "literal", "value": literal_of(entry.get("pattern", ""))[:2000]}
    description = entry.get("description") or " | ".join(
        part for part in (
            entry.get("name", ""),
            entry.get("cve", ""),
            f"wzorzec regex: {entry.get('pattern', '')}",
        ) if part
    )
    print(json.dumps({
        "id": identifier,
        "name": (entry.get("name") or identifier)[:200],
        "source": entry.get("source") or source_of(entry),
        "category": (entry.get("category") or entry.get("owasp_category") or "unclassified")[:80],
        "action": "block" if entry.get("action") == "block" else "monitor",
        "target": entry.get("target") or target_of(entry.get("target_component", "")),
        "match": match,
        "description": description[:2000],
        "enabled": True,
    }))
PY
done

created=0
existing=0
failed=0

while IFS= read -r signature; do
  [[ -z "$signature" ]] && continue
  identifier="$(printf '%s' "$signature" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')"
  code="$(curl -s -o "$response" -w '%{http_code}' -m 10 -X POST "$CONTROLPLANE_URL/api/v1/signatures" \
    -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' -d "$signature")"
  case "$code" in
    200|201) created=$((created + 1)); echo "  + $identifier" ;;
    409)     existing=$((existing + 1)) ;;
    401|403) echo "import-signatures: HTTP $code - sprawdz ADMIN_TOKEN" >&2; exit 1 ;;
    000)     echo "import-signatures: brak odpowiedzi pod $CONTROLPLANE_URL - uruchom: make up" >&2; exit 1 ;;
    404|405) echo "import-signatures: HTTP $code - obraz control plane nie ma POST /api/v1/signatures;" >&2
             echo "  przebuduj: sudo docker compose up -d --build controlplane" >&2; exit 1 ;;
    *)       failed=$((failed + 1)); echo "  ! $identifier: HTTP $code $(head -c 160 "$response")" >&2 ;;
  esac
done <"$payload"

echo "import-signatures: dodano $created, juz bylo $existing, bledy $failed (nic nie usunieto)"
[[ "$failed" -eq 0 ]]
