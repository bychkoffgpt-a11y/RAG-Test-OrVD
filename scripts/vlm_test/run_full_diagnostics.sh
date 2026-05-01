#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="${API_URL:-http://localhost:8000}"
MODEL="${MODEL:-local-vlm}"
CASES_FILE="${CASES_FILE:-${ROOT_DIR}/vlm_test_cases.json}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/out/$(date -u +%Y%m%dT%H%M%SZ)}"
HIT_THRESHOLD="${HIT_THRESHOLD:-0.6}"
RAG_SCOPE="${RAG_SCOPE:-none}"
VISION_PROMPT="${VISION_PROMPT:-Проанализируй изображение, распознай весь текст, опиши картинки и графические изображения.}"
MAX_TOKENS="${MAX_TOKENS:-1024}"
TEMPERATURE="${TEMPERATURE:-0.0}"

if [[ -e "$OUT_DIR" ]]; then
  echo "ERROR: output directory already exists: $OUT_DIR"
  echo "Choose a different timestamp or set OUT_DIR to a unique path."
  exit 1
fi

mkdir -p "$OUT_DIR"

GIT_SHA="$(git rev-parse --short HEAD)"
GIT_BRANCH="$(git branch --show-current)"
RUN_META_PATH="${OUT_DIR}/run_meta.txt"

{
  echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_sha_short=${GIT_SHA}"
  echo "git_branch=${GIT_BRANCH}"
  echo "api_url=${API_URL}"
  echo ""
  echo "[VISION_ENV]"
  env | sort | awk -F= '/^VISION_/ {print $1"="$2}'
} > "$RUN_META_PATH"

echo "Saved run metadata: ${RUN_META_PATH}"

echo "[1/8] /ask run"
python3 "${ROOT_DIR}/run_vlm_ask.py" \
  --api-url "$API_URL" \
  --cases "$CASES_FILE" \
  --scope "$RAG_SCOPE" \
  --out "${OUT_DIR}/vlm_ask_results.jsonl"

echo "[2/8] /v1/chat/completions run"
python3 "${ROOT_DIR}/run_vlm_chat_completions.py" \
  --api-url "$API_URL" \
  --model "$MODEL" \
  --cases "$CASES_FILE" \
  --rag-scope "$RAG_SCOPE" \
  --out "${OUT_DIR}/vlm_chat_results.jsonl"

echo "[3/8] /vision/debug/recognize run"
python3 "${ROOT_DIR}/run_vlm_vision_debug.py" \
  --api-url "$API_URL" \
  --cases "$CASES_FILE" \
  --prompt "$VISION_PROMPT" \
  --max-tokens "$MAX_TOKENS" \
  --temperature "$TEMPERATURE" \
  --out "${OUT_DIR}/vlm_vision_debug_results.jsonl"

echo "[4/8] baseline score (/ask)"
python3 "${ROOT_DIR}/score_vlm_results.py" \
  --input "${OUT_DIR}/vlm_ask_results.jsonl" \
  --out-json "${OUT_DIR}/vlm_ask_score_summary.json" \
  --out-csv "${OUT_DIR}/vlm_ask_score_per_case.csv"

echo "[5/8] baseline score (/chat)"
python3 "${ROOT_DIR}/score_vlm_results.py" \
  --input "${OUT_DIR}/vlm_chat_results.jsonl" \
  --out-json "${OUT_DIR}/vlm_chat_score_summary.json" \
  --out-csv "${OUT_DIR}/vlm_chat_score_per_case.csv"

echo "[6/8] baseline score (/vision/debug/recognize)"
python3 "${ROOT_DIR}/score_vlm_results.py" \
  --input "${OUT_DIR}/vlm_vision_debug_results.jsonl" \
  --out-json "${OUT_DIR}/vlm_vision_debug_score_summary.json" \
  --out-csv "${OUT_DIR}/vlm_vision_debug_score_per_case.csv"

echo "[7/8] v2 score (/ask + /chat + /vision/debug/recognize)"
python3 "${ROOT_DIR}/score_vlm_results_v2.py" \
  --input "${OUT_DIR}/vlm_ask_results.jsonl" \
  --hit-threshold "$HIT_THRESHOLD" \
  --out-json "${OUT_DIR}/vlm_ask_score_v2_summary.json" \
  --out-csv "${OUT_DIR}/vlm_ask_score_v2_per_case.csv"

python3 "${ROOT_DIR}/score_vlm_results_v2.py" \
  --input "${OUT_DIR}/vlm_chat_results.jsonl" \
  --hit-threshold "$HIT_THRESHOLD" \
  --out-json "${OUT_DIR}/vlm_chat_score_v2_summary.json" \
  --out-csv "${OUT_DIR}/vlm_chat_score_v2_per_case.csv"

python3 "${ROOT_DIR}/score_vlm_results_v2.py" \
  --input "${OUT_DIR}/vlm_vision_debug_results.jsonl" \
  --hit-threshold "$HIT_THRESHOLD" \
  --out-json "${OUT_DIR}/vlm_vision_debug_score_v2_summary.json" \
  --out-csv "${OUT_DIR}/vlm_vision_debug_score_v2_per_case.csv"

echo "[8/8] comparison report"
python3 "${ROOT_DIR}/summarize_vlm_diagnostics.py" \
  --ask-summary "${OUT_DIR}/vlm_ask_score_v2_summary.json" \
  --chat-summary "${OUT_DIR}/vlm_chat_score_v2_summary.json" \
  --vision-summary "${OUT_DIR}/vlm_vision_debug_score_v2_summary.json" \
  --git-sha "$GIT_SHA" \
  --git-branch "$GIT_BRANCH" \
  --out-markdown "${OUT_DIR}/comparison.md"

echo "\nDone. Output directory: ${OUT_DIR}"
echo "- comparison: ${OUT_DIR}/comparison.md"
echo "- ask v2 summary: ${OUT_DIR}/vlm_ask_score_v2_summary.json"
echo "- chat v2 summary: ${OUT_DIR}/vlm_chat_score_v2_summary.json"
echo "- vision debug v2 summary: ${OUT_DIR}/vlm_vision_debug_score_v2_summary.json"
