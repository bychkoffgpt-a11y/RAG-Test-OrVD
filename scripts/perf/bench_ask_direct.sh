#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
ITER="${ITER:-8}"
SLEEP_SEC="${SLEEP_SEC:-0.5}"
TOP_K="${TOP_K:-6}"
SCOPE="${SCOPE:-all}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"
QUESTION="${QUESTION:-Добрый день. В программе СВР АНС... Что с 11.02.2026?}"
MODEL_ID="${MODEL_ID:-local-rag-model}"
RERANKER_EXPECTED="${RERANKER_EXPECTED:-unknown}"
VISION_MODE_EXPECTED="${VISION_MODE_EXPECTED:-unknown}"
WARMUP="${WARMUP:-1}"

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "ERROR: IMAGE_PATH not found: $IMAGE_PATH"
  exit 1
fi

OUT_DIR="${1:-data/rag_traces/ui_overhead/ask_direct_$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"
echo "[]" > "$OUT_DIR/runs.json"

for i in $(seq 1 "$ITER"); do
  START_NS=$(date +%s%N)
  HTTP_CODE=$(curl -sS -o "$OUT_DIR/resp_$i.json" -w "%{http_code}" \
    -X POST "${API_URL}/ask" \
    -H 'Content-Type: application/json' \
    -d "{
      \"question\": \"${QUESTION//\"/\\\"}\",
      \"top_k\": ${TOP_K},
      \"scope\": \"${SCOPE}\",
      \"model\": \"${MODEL_ID}\",
      \"attachments\": [{\"image_path\":\"${IMAGE_PATH}\"}]
    }")
  END_NS=$(date +%s%N)
  LAT_MS=$(( (END_NS - START_NS) / 1000000 ))

  jq --argjson i "$i" --arg code "$HTTP_CODE" --argjson ms "$LAT_MS" \
    '. + [{"iteration":$i,"http_code":($code|tonumber),"latency_ms":$ms}]' \
    "$OUT_DIR/runs.json" > "$OUT_DIR/runs.tmp.json" && mv "$OUT_DIR/runs.tmp.json" "$OUT_DIR/runs.json"

  echo "[ask] #$i code=$HTTP_CODE latency=${LAT_MS}ms"
  sleep "$SLEEP_SEC"
done

jq --arg q "$QUESTION" --arg img "$IMAGE_PATH" --arg model "$MODEL_ID" \
   --arg scope "$SCOPE" --argjson topk "$TOP_K" --arg rer "$RERANKER_EXPECTED" --arg vis "$VISION_MODE_EXPECTED" --argjson warm "$WARMUP" '{
  meta:{endpoint:"/ask",question:$q,image_path:$img,model_id:$model,scope:$scope,top_k:$topk,reranker_expected:$rer,vision_mode_expected:$vis,warmup_count:$warm},
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
}' "$OUT_DIR/runs.json" > "$OUT_DIR/summary.json"

OK_COUNT="$(jq -r '.ok' "$OUT_DIR/summary.json")"
if [[ "$OK_COUNT" -eq 0 ]]; then
  echo "[FAIL] direct ask benchmark failed: no successful (2xx) responses"
  cat "$OUT_DIR/summary.json"
  exit 1
fi

echo "[OK] direct ask results: $OUT_DIR"
cat "$OUT_DIR/summary.json"
