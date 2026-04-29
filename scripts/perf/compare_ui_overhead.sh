#!/usr/bin/env bash
set -euo pipefail

ASK_SUMMARY="${1:?path to ask direct summary.json}"
WEBUI_SUMMARY="${2:?path to openwebui summary.json}"

ASK_MEAN=$(jq -r '.mean_ms' "$ASK_SUMMARY")
ASK_P95=$(jq -r '.p95_ms' "$ASK_SUMMARY")
UI_MEAN=$(jq -r '.mean_ms' "$WEBUI_SUMMARY")
UI_P95=$(jq -r '.p95_ms' "$WEBUI_SUMMARY")

DELTA_MEAN=$(python3 - <<PY
a=float("$ASK_MEAN"); b=float("$UI_MEAN"); print(round(b-a,2))
PY
)
DELTA_P95=$(python3 - <<PY
a=float("$ASK_P95"); b=float("$UI_P95"); print(round(b-a,2))
PY
)

echo "=== UI overhead ==="
echo "ask_direct mean=${ASK_MEAN}ms p95=${ASK_P95}ms"
echo "openwebui  mean=${UI_MEAN}ms p95=${UI_P95}ms"
echo "delta      mean=${DELTA_MEAN}ms p95=${DELTA_P95}ms"
