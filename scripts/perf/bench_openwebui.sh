#!/usr/bin/env bash
set -euo pipefail

# =========================
# OpenWebUI benchmark script
# Fixes:
# 1) explicit runtime bearer token (not assuming .env WEBUI_API_KEY is valid)
# 2) preflight auth/endpoint/model validation
# 3) fail status/exit code when no successful requests
# =========================

WEBUI_URL="${WEBUI_URL:-http://localhost:3000}"
ITER="${ITER:-8}"
SLEEP_SEC="${SLEEP_SEC:-0.5}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"
QUESTION="${QUESTION:-Добрый день. В программе СВР АНС... Что с 11.02.2026?}"
MODEL_ID="${MODEL_ID:-local-rag-model}"

# Runtime bearer token for OpenWebUI API
# Preferred var:
WEBUI_BEARER_TOKEN="${WEBUI_BEARER_TOKEN:-${OPENWEBUI_TOKEN:-${WEBUI_KEY:-}}}"

if [[ -z "${WEBUI_BEARER_TOKEN}" ]]; then
  echo "ERROR: set WEBUI_BEARER_TOKEN (or OPENWEBUI_TOKEN / WEBUI_KEY)."
  echo "Example: export WEBUI_BEARER_TOKEN='...'"
  exit 1
fi

if [[ ! -f "${IMAGE_PATH}" ]]; then
  echo "ERROR: IMAGE_PATH not found: ${IMAGE_PATH}"
  exit 1
fi

for cmd in curl jq; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: missing dependency: ${cmd}"
    exit 1
  fi
done

OUT_DIR="${1:-data/rag_traces/ui_overhead/openwebui_$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${OUT_DIR}"
echo "[]" > "${OUT_DIR}/runs.json"

AUTH_HEADER="Authorization: Bearer ${WEBUI_BEARER_TOKEN}"

# ---------- preflight ----------
PREFLIGHT_FILE="${OUT_DIR}/preflight.json"
PREFLIGHT_BODY="${OUT_DIR}/preflight_resp.json"

PREFLIGHT_CODE=$(curl -sS -o "${PREFLIGHT_BODY}" -w "%{http_code}" \
  -X GET "${WEBUI_URL}/api/models" \
  -H "${AUTH_HEADER}")

jq -n \
  --arg url "${WEBUI_URL}/api/models" \
  --arg code "${PREFLIGHT_CODE}" \
  --arg model "${MODEL_ID}" \
  '{url:$url,http_code:($code|tonumber),model_id:$model}' > "${PREFLIGHT_FILE}"

if [[ "${PREFLIGHT_CODE}" -lt 200 || "${PREFLIGHT_CODE}" -ge 300 ]]; then
  echo "[FAIL] preflight auth/endpoint check failed: ${WEBUI_URL}/api/models code=${PREFLIGHT_CODE}"
  echo "Hint: token type/scope may be wrong for OpenWebUI bearer auth."
  echo "Response preview:"
  head -c 500 "${PREFLIGHT_BODY}" || true
  echo
  exit 1
fi

# Optional model presence check (best-effort; does not break if response shape is unknown)
if ! jq -e --arg m "${MODEL_ID}" '
  (.. | objects | select(has("id")) | .id == $m) // false
' "${PREFLIGHT_BODY}" >/dev/null 2>&1; then
  echo "[WARN] MODEL_ID='${MODEL_ID}' was not detected in /api/models response."
  echo "       Requests may fail with non-2xx if model name is invalid."
fi

# ---------- benchmark ----------
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

jq '{
  count: length,
  ok: (map(select(.http_code>=200 and .http_code<300))|length),
  error_count: (map(select(.http_code<200 or .http_code>=300))|length),
  first_error_code: ( [ .[] | select(.http_code<200 or .http_code>=300) | .http_code ] | .[0] // null ),
  p50_ms: (map(.latency_ms)|sort|.[(length*0.50|floor)]),
  p95_ms: (map(.latency_ms)|sort|.[(length*0.95|floor)]),
  mean_ms: (map(.latency_ms)|add/length)
}' "${OUT_DIR}/runs.json" > "${OUT_DIR}/summary.json"

OK_COUNT="$(jq -r '.ok' "${OUT_DIR}/summary.json")"
FIRST_ERR="$(jq -r '.first_error_code' "${OUT_DIR}/summary.json")"

if [[ "${OK_COUNT}" -eq 0 ]]; then
  echo "[FAIL] openwebui benchmark failed: no successful (2xx) responses"
  echo "Results: ${OUT_DIR}"
  cat "${OUT_DIR}/summary.json"
  if [[ "${FIRST_ERR}" == "401" || "${FIRST_ERR}" == "403" ]]; then
    echo "Hint: bearer token is invalid for this endpoint or has insufficient scope."
  fi
  exit 1
fi

echo "[OK] openwebui results: ${OUT_DIR}"
cat "${OUT_DIR}/summary.json"