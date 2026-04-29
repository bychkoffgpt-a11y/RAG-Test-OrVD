#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <ask_summary.json> <openwebui_summary.json>"
  exit 1
fi

ASK="$1"
UI="$2"

for f in "$ASK" "$UI"; do
  [[ -f "$f" ]] || { echo "ERROR: missing file: $f"; exit 1; }
done

# Ensure comparable conditions
for key in question image_path model_id scope top_k reranker_expected vision_mode_expected warmup_count; do
  A=$(jq -r ".meta.${key}" "$ASK")
  B=$(jq -r ".meta.${key}" "$UI")
  if [[ "$A" != "$B" ]]; then
    echo "ERROR: mismatch in meta.${key}: ask='${A}' ui='${B}'"
    exit 1
  fi
done

ASK_MEAN=$(jq -r '.mean_ms_steady // .mean_ms_all' "$ASK")
ASK_P95=$(jq -r '.p95_ms_steady // .p95_ms_all' "$ASK")
UI_MEAN=$(jq -r '.mean_ms_steady // .mean_ms_all' "$UI")
UI_P95=$(jq -r '.p95_ms_steady // .p95_ms_all' "$UI")

DELTA_MEAN=$(python3 - <<PY
print(round(float("$UI_MEAN") - float("$ASK_MEAN"), 2))
PY
)
DELTA_P95=$(python3 - <<PY
print(round(float("$UI_P95") - float("$ASK_P95"), 2))
PY
)

echo "=== UI overhead (steady-state, warmup removed) ==="
echo "ask_direct mean=${ASK_MEAN}ms p95=${ASK_P95}ms"
echo "openwebui  mean=${UI_MEAN}ms p95=${UI_P95}ms"
echo "delta      mean=${DELTA_MEAN}ms p95=${DELTA_P95}ms"
