#!/usr/bin/env bash
# Lint: containers must not install packages or download models AT RUNTIME. Usage: make offline-check
# Build-time steps (RUN pip/uv/apt, model bake in RUN python -m app.download) are fine and expected.
set -uo pipefail
cd "$(dirname "$0")/.."

pass=0; fail=0
# Patterns that must never appear where the container *starts* (CMD/ENTRYPOINT/compose command).
RUNTIME_DL='pip3?[[:space:]]+install|apt-get[[:space:]]+(update|install)|apk[[:space:]]+add|npm[[:space:]]+install|yarn[[:space:]]+add|snapshot_download|from_pretrained|app\.download|ollama[[:space:]]+pull|huggingface-cli[[:space:]]+download'

echo "== Dockerfile CMD/ENTRYPOINT =="
for df in $(find . -name Dockerfile -not -path './.git/*' | sort); do
  runtime=$(grep -nE '^[[:space:]]*(CMD|ENTRYPOINT)' "$df" | grep -E "$RUNTIME_DL" || true)
  if [[ -z "$runtime" ]]; then
    printf '  PASS  %-34s clean\n' "$df"; pass=$((pass+1))
  else
    printf '  FAIL  %-34s %s\n' "$df" "$(tr '\n' ';' <<<"$runtime")"; fail=$((fail+1))
  fi
done

echo "== compose command/entrypoint =="
runtime=$(grep -nE '^[[:space:]]*(command|entrypoint):' docker-compose.yaml | grep -E "$RUNTIME_DL" || true)
if [[ -z "$runtime" ]]; then
  printf '  PASS  %-34s clean\n' "docker-compose.yaml"; pass=$((pass+1))
else
  printf '  FAIL  %-34s %s\n' "docker-compose.yaml" "$(tr '\n' ';' <<<"$runtime")"; fail=$((fail+1))
fi

echo "== model + assets baked =="
SEM=semantic-service/Dockerfile
if grep -qE '^RUN .*app\.download' "$SEM" && grep -q 'MODELS_OFFLINE=1' "$SEM"; then
  printf '  PASS  %-34s model baked at build + MODELS_OFFLINE=1\n' "$SEM"; pass=$((pass+1))
else
  printf '  FAIL  %-34s model not baked / MODELS_OFFLINE missing\n' "$SEM"; fail=$((fail+1))
fi

cdns=$(grep -rInE --exclude-dir=node_modules 'https?://(cdn\.|unpkg|cdnjs|jsdelivr)' dashboard/ 2>/dev/null || true)
if [[ -z "$cdns" ]]; then
  printf '  PASS  %-34s no CDN references\n' "dashboard/"; pass=$((pass+1))
else
  printf '  FAIL  %-34s CDN refs: %s\n' "dashboard/" "$(tr '\n' ';' <<<"$cdns")"; fail=$((fail+1))
fi

echo
echo "offline-check: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
