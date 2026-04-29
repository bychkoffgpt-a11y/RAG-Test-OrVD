#!/usr/bin/env bash
set -euo pipefail

WEBUI_URL="${WEBUI_URL:-http://localhost:3000}"
ITER="${ITER:-8}"
WARMUP_ITER="${WARMUP_ITER:-2}"
SLEEP_SEC="${SLEEP_SEC:-0.5}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"
QUESTION="${QUESTION:-Добрый день. В программе СВР АНС... Что с 11.02.2026?}"
MODEL_ID="${MODEL_ID:-local-rag-model}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-512}"
TOP_K="${TOP_K:-6}"
SCOPE="${SCOPE:-all}"
TEXT_ONLY="${TEXT_ONLY:-0}"
WEBUI_BEARER_TOKEN="${WEBUI_BEARER_TOKEN:-${OPENWEBUI_TOKEN:-${WEBUI_KEY:-}}}"

if [[ -z "${WEBUI_BEARER_TOKEN}" ]]; then
  echo "ERROR: set WEBUI_BEARER_TOKEN (or OPENWEBUI_TOKEN / WEBUI_KEY)."
  exit 1
fi
if [[ "$TEXT_ONLY" != "1" && ! -f "${IMAGE_PATH}" ]]; then
  echo "ERROR: IMAGE_PATH not found: ${IMAGE_PATH}"
  exit 1
fi

OUT_DIR="${1:-data/rag_traces/ui_overhead/openwebui_$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${OUT_DIR}"
echo "[]" > "${OUT_DIR}/runs.json"
AUTH_HEADER="Authorization: Bearer ${WEBUI_BEARER_TOKEN}"

jq -n \
  --arg script "bench_openwebui.sh" \
  --arg sut_endpoint "/api/chat/completions" \
  --arg path_type "ui_proxy" \
  --arg question "$QUESTION" \
  --argjson top_k "$TOP_K" \
  --arg scope "$SCOPE" \
  --argjson temperature "$TEMPERATURE" \
  --argjson max_tokens "$MAX_TOKENS" \
  --argjson text_only "$TEXT_ONLY" \
  --arg image_path "$IMAGE_PATH" \
  --arg webui_url "$WEBUI_URL" \
  --arg model_id "$MODEL_ID" \
  '{script:$script,sut_endpoint:$sut_endpoint,path_type:$path_type,webui_url:$webui_url,model_id:$model_id,question:$question,retrieval:{top_k:$top_k,scope:$scope},generation:{temperature:$temperature,max_tokens:$max_tokens},text_only:($text_only==1),image_path:$image_path}' \
  > "$OUT_DIR/config.json"

PREFLIGHT_CODE=$(curl -sS -o "${OUT_DIR}/preflight_resp.json" -w "%{http_code}" -X GET "${WEBUI_URL}/api/models" -H "${AUTH_HEADER}")
if [[ "${PREFLIGHT_CODE}" -lt 200 || "${PREFLIGHT_CODE}" -ge 300 ]]; then
  echo "[FAIL] preflight failed code=${PREFLIGHT_CODE}"; exit 1
fi

run_once() {
  local i="$1"
  local phase="$2"
  local body_file="$OUT_DIR/req_${phase}_${i}.json"

  if [[ "$TEXT_ONLY" == "1" ]]; then
    jq -n --arg model "$MODEL_ID" --arg q "$QUESTION" --argjson mt "$MAX_TOKENS" --argjson temp "$TEMPERATURE" --argjson k "$TOP_K" --arg s "$SCOPE" \
      '{model:$model,messages:[{role:"system",content:("retrieval scope="+$s+" top_k="+($k|tostring))},{role:"user",content:[{type:"text",text:$q}]}],stream:false,max_tokens:$mt,temperature:$temp}' > "$body_file"
  else
    jq -n --arg model "$MODEL_ID" --arg q "$QUESTION" --arg img "$IMAGE_PATH" --argjson mt "$MAX_TOKENS" --argjson temp "$TEMPERATURE" --argjson k "$TOP_K" --arg s "$SCOPE" \
      '{model:$model,messages:[{role:"system",content:("retrieval scope="+$s+" top_k="+($k|tostring))},{role:"user",content:[{type:"text",text:$q},{type:"image_url",image_url:{url:("file://"+$img)}}]}],stream:false,max_tokens:$mt,temperature:$temp}' > "$body_file"
  fi

  START_NS=$(date +%s%N)
  HTTP_CODE=$(curl -sS -o "${OUT_DIR}/resp_${phase}_${i}.json" -w "%{http_code}" \
    -X POST "${WEBUI_URL}/api/chat/completions" \
    -H "${AUTH_HEADER}" -H 'Content-Type: application/json' \
    --data-binary "@$body_file")
  END_NS=$(date +%s%N)
  LAT_MS=$(( (END_NS - START_NS) / 1000000 ))

  jq --argjson i "$i" --arg code "$HTTP_CODE" --argjson ms "$LAT_MS" --arg phase "$phase" \
    '. + [{"iteration":$i,"phase":$phase,"http_code":($code|tonumber),"latency_ms":$ms}]' \
    "${OUT_DIR}/runs.json" > "${OUT_DIR}/runs.tmp.json" && mv "${OUT_DIR}/runs.tmp.json" "${OUT_DIR}/runs.json"

  echo "[webui/${phase}] #${i} code=${HTTP_CODE} latency=${LAT_MS}ms"
  sleep "${SLEEP_SEC}"
}

for i in $(seq 1 "$WARMUP_ITER"); do run_once "$i" "warmup"; done
for i in $(seq 1 "$ITER"); do run_once "$i" "measure"; done

jq '{
  count: length,
  measure_count: (map(select(.phase=="measure"))|length),
  warmup_count: (map(select(.phase=="warmup"))|length),
  ok: (map(select(.phase=="measure" and .http_code>=200 and .http_code<300))|length),
  error_count: (map(select(.phase=="measure" and (.http_code<200 or .http_code>=300)))|length),
  non2xx_codes_hist: (map(select(.phase=="measure" and (.http_code<200 or .http_code>=300))|.http_code) | group_by(.) | map({code: .[0], count:length})),
  all_requests_mean_ms: (map(select(.phase=="measure")|.latency_ms)|if length>0 then (add/length) else null end),
  ok_requests_mean_ms: (map(select(.phase=="measure" and .http_code>=200 and .http_code<300)|.latency_ms)|if length>0 then (add/length) else null end),
  ok_requests_p50_ms: (map(select(.phase=="measure" and .http_code>=200 and .http_code<300)|.latency_ms)|sort|if length>0 then .[(length*0.50|floor)] else null end),
  ok_requests_p95_ms: (map(select(.phase=="measure" and .http_code>=200 and .http_code<300)|.latency_ms)|sort|if length>0 then .[(length*0.95|floor)] else null end)
}' "${OUT_DIR}/runs.json" > "${OUT_DIR}/summary.json"

echo "[OK] openwebui results: ${OUT_DIR}"
cat "${OUT_DIR}/summary.json"
