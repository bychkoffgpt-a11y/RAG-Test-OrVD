#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
ITER="${ITER:-8}"
SLEEP_SEC="${SLEEP_SEC:-0.5}"
TOP_K="${TOP_K:-6}"
SCOPE="${SCOPE:-all}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"
QUESTION="${QUESTION:-Добрый день. В программе СВР АНС... Что с 11.02.2026?}"

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

jq '{
  count: length,
  ok: (map(select(.http_code>=200 and .http_code<300))|length),
  p50_ms: (map(.latency_ms)|sort|.[(length*0.50|floor)]),
  p95_ms: (map(.latency_ms)|sort|.[(length*0.95|floor)]),
  mean_ms: (map(.latency_ms)|add/length)
}' "$OUT_DIR/runs.json" > "$OUT_DIR/summary.json"

echo "[OK] direct ask results: $OUT_DIR"
cat "$OUT_DIR/summary.json"