#!/usr/bin/env bash
set -euo pipefail

ASK_SUMMARY="${1:?path to ask direct summary.json}"
WEBUI_SUMMARY="${2:?path to openwebui summary.json}"
ASK_CONFIG="$(dirname "$ASK_SUMMARY")/config.json"
WEBUI_CONFIG="$(dirname "$WEBUI_SUMMARY")/config.json"

if [[ ! -f "$ASK_CONFIG" || ! -f "$WEBUI_CONFIG" ]]; then
  echo "ERROR: config.json is required in both benchmark directories"
  exit 1
fi

ASK_GEN=$(jq -c '.generation' "$ASK_CONFIG")
WEB_GEN=$(jq -c '.generation' "$WEBUI_CONFIG")
ASK_RET=$(jq -c '.retrieval' "$ASK_CONFIG")
WEB_RET=$(jq -c '.retrieval' "$WEBUI_CONFIG")
ASK_TXT=$(jq -r '.text_only' "$ASK_CONFIG")
WEB_TXT=$(jq -r '.text_only' "$WEBUI_CONFIG")

if [[ "$ASK_GEN" != "$WEB_GEN" || "$ASK_RET" != "$WEB_RET" || "$ASK_TXT" != "$WEB_TXT" ]]; then
  echo "ERROR: benchmark configs are not comparable"
  echo "direct generation:  $ASK_GEN"
  echo "webui generation:   $WEB_GEN"
  echo "direct retrieval:   $ASK_RET"
  echo "webui retrieval:    $WEB_RET"
  echo "direct text_only:   $ASK_TXT"
  echo "webui text_only:    $WEB_TXT"
  exit 1
fi

ASK_OK_MEAN=$(jq -r '.ok_requests_mean_ms' "$ASK_SUMMARY")
ASK_OK_P95=$(jq -r '.ok_requests_p95_ms' "$ASK_SUMMARY")
WEB_OK_MEAN=$(jq -r '.ok_requests_mean_ms' "$WEBUI_SUMMARY")
WEB_OK_P95=$(jq -r '.ok_requests_p95_ms' "$WEBUI_SUMMARY")
ASK_OK_RATE=$(jq -r 'if .measure_count>0 then (.ok/.measure_count) else 0 end' "$ASK_SUMMARY")
WEB_OK_RATE=$(jq -r 'if .measure_count>0 then (.ok/.measure_count) else 0 end' "$WEBUI_SUMMARY")

DELTA_MEAN=$(python3 - <<PY
print(round(float("$WEB_OK_MEAN")-float("$ASK_OK_MEAN"),2))
PY
)
DELTA_P95=$(python3 - <<PY
print(round(float("$WEB_OK_P95")-float("$ASK_OK_P95"),2))
PY
)

echo "=== UI overhead (ok-only) ==="
echo "ask_direct mean=${ASK_OK_MEAN}ms p95=${ASK_OK_P95}ms ok_rate=${ASK_OK_RATE}"
echo "openwebui  mean=${WEB_OK_MEAN}ms p95=${WEB_OK_P95}ms ok_rate=${WEB_OK_RATE}"
echo "delta      mean=${DELTA_MEAN}ms p95=${DELTA_P95}ms"
