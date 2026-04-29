#!/usr/bin/env bash
set -euo pipefail

WEBUI_URL="${WEBUI_URL:-http://localhost:3000}"
ITER="${ITER:-8}"
SLEEP_SEC="${SLEEP_SEC:-0.5}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"
QUESTION="${QUESTION:-Добрый день. В программе СВР АНС... Что с 11.02.2026?}"
MODEL_ID="${MODEL_ID:-local-rag-model}"
TOP_K="${TOP_K:-6}"
SCOPE="${SCOPE:-all}"
RERANKER_EXPECTED="${RERANKER_EXPECTED:-unknown}"
VISION_MODE_EXPECTED="${VISION_MODE_EXPECTED:-unknown}"
WARMUP="${WARMUP:-1}"
WEBUI_BEARER_TOKEN="${WEBUI_BEARER_TOKEN:-${OPENWEBUI_TOKEN:-${WEBUI_KEY:-}}}"

if [[ -z "${WEBUI_BEARER_TOKEN}" ]]; then
  echo "ERROR: set WEBUI_BEARER_TOKEN (or OPENWEBUI_TOKEN / WEBUI_KEY)."
  exit 1
fi
if [[ ! -f "${IMAGE_PATH}" ]]; then
  echo "ERROR: IMAGE_PATH not found: ${IMAGE_PATH}"
  exit 1
fi

OUT_DIR="${1:-data/rag_traces/ui_overhead/openwebui_$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${OUT_DIR}"
echo "[]" > "${OUT_DIR}/runs.json"
AUTH_HEADER="Authorization: Bearer ${WEBUI_BEARER_TOKEN}"

PREFLIGHT_CODE=$(curl -sS -o "${OUT_DIR}/preflight_resp.json" -w "%{http_code}" \
  -X GET "${WEBUI_URL}/api/models" \
  -H "${AUTH_HEADER}")

if [[ "${PREFLIGHT_CODE}" -lt 200 || "${PREFLIGHT_CODE}" -ge 300 ]]; then
  echo "[FAIL] preflight auth/endpoint check failed: ${WEBUI_URL}/api/models code=${PREFLIGHT_CODE}"
  head -c 500 "${OUT_DIR}/preflight_resp.json" || true
  echo
  exit 1
fi

for i in $(seq 1 "${ITER}"); do
  START_NS=$(date +%s%N)
  HTTP_CODE=$(curl -sS -o "${OUT_DIR}/resp_${i}.json" -w "%{http_code}" \
    -X POST "${WEBUI_URL}/api/chat/completions" \
    -H "${AUTH_HEADER}" \
    -H 'Content-Type: application/json' \
    -d "{
      \"model\": \"${MODEL_ID}\",
      \"messages\": [{
        \"role\":\"user\",
        \"content\": [
          {\"type\":\"text\",\"text\":\"${QUESTION//\"/\\\"}\"},
          {\"type\":\"image_url\",\"image_url\":{\"url\":\"file://${IMAGE_PATH}\"}}
        ]
      }],
      \"stream\": false,
      \"max_tokens\": 512,
      \"temperature\": 0.1
    }")
  END_NS=$(date +%s%N)
  LAT_MS=$(( (END_NS - START_NS) / 1000000 ))

  jq --argjson i "${i}" --arg code "${HTTP_CODE}" --argjson ms "${LAT_MS}" \
    '. + [{"iteration":$i,"http_code":($code|tonumber),"latency_ms":$ms}]' \
    "${OUT_DIR}/runs.json" > "${OUT_DIR}/runs.tmp.json" && mv "${OUT_DIR}/runs.tmp.json" "${OUT_DIR}/runs.json"

  echo "[webui] #${i} code=${HTTP_CODE} latency=${LAT_MS}ms"
  sleep "${SLEEP_SEC}"
done

jq --arg q "$QUESTION" --arg img "$IMAGE_PATH" --arg model "$MODEL_ID" --arg scope "$SCOPE" \
   --argjson topk "$TOP_K" --arg rer "$RERANKER_EXPECTED" --arg vis "$VISION_MODE_EXPECTED" --argjson warm "$WARMUP" '{
  meta:{endpoint:"/api/chat/completions",question:$q,image_path:$img,model_id:$model,scope:$scope,top_k:$topk,reranker_expected:$rer,vision_mode_expected:$vis,warmup_count:$warm},
  count: length,
  ok: (map(select(.http_code>=200 and .http_code<300))|length),
  error_count: (map(select(.http_code<200 or .http_code>=300))|length),
  first_error_code: ([ .[] | select(.http_code<200 or .http_code>=300) | .http_code ] | .[0] // null),
  p50_ms_all: (map(.latency_ms)|sort|.[(length*0.50|floor)]),
  p95_ms_all: (map(.latency_ms)|sort|.[(length*0.95|floor)]),
  mean_ms_all: (map(.latency_ms)|add/length),
  p50_ms_steady: (map(select(.iteration > $warm).latency_ms)|sort| if length>0 then .[(length*0.50|floor)] else null end),
  p95_ms_steady: (map(select(.iteration > $warm).latency_ms)|sort| if length>0 then .[(length*0.95|floor)] else null end),
  mean_ms_steady: (map(select(.iteration > $warm).latency_ms)| if length>0 then add/length else null end)
}' "${OUT_DIR}/runs.json" > "${OUT_DIR}/summary.json"

OK_COUNT="$(jq -r '.ok' "${OUT_DIR}/summary.json")"
if [[ "${OK_COUNT}" -eq 0 ]]; then
  echo "[FAIL] openwebui benchmark failed: no successful (2xx) responses"
  cat "${OUT_DIR}/summary.json"
  exit 1
fi

echo "[OK] openwebui results: ${OUT_DIR}"
cat "${OUT_DIR}/summary.json"
