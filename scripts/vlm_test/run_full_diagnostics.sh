#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="${API_URL:-http://localhost:8000}"
MODEL="${MODEL:-local-vlm}"
CASES_FILE="${CASES_FILE:-${ROOT_DIR}/vlm_test_cases.json}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/out/$(date -u +%Y%m%dT%H%M%SZ)}"
HIT_THRESHOLD="${HIT_THRESHOLD:-0.6}"

mkdir -p "$OUT_DIR"

echo "[1/6] /ask run"
python3 "${ROOT_DIR}/run_vlm_ask.py" \
  --api-url "$API_URL" \
  --cases "$CASES_FILE" \
  --out "${OUT_DIR}/vlm_ask_results.jsonl"

echo "[2/6] /v1/chat/completions run"
python3 "${ROOT_DIR}/run_vlm_chat_completions.py" \
  --api-url "$API_URL" \
  --model "$MODEL" \
  --cases "$CASES_FILE" \
  --out "${OUT_DIR}/vlm_chat_results.jsonl"

echo "[3/6] baseline score (/ask)"
python3 "${ROOT_DIR}/score_vlm_results.py" \
  --input "${OUT_DIR}/vlm_ask_results.jsonl" \
  --out-json "${OUT_DIR}/vlm_ask_score_summary.json" \
  --out-csv "${OUT_DIR}/vlm_ask_score_per_case.csv"

echo "[4/6] baseline score (/chat)"
python3 "${ROOT_DIR}/score_vlm_results.py" \
  --input "${OUT_DIR}/vlm_chat_results.jsonl" \
  --out-json "${OUT_DIR}/vlm_chat_score_summary.json" \
  --out-csv "${OUT_DIR}/vlm_chat_score_per_case.csv"

echo "[5/6] v2 score (/ask + /chat)"
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

echo "[6/6] comparison report"
python3 "${ROOT_DIR}/summarize_vlm_diagnostics.py" \
  --ask-summary "${OUT_DIR}/vlm_ask_score_v2_summary.json" \
  --chat-summary "${OUT_DIR}/vlm_chat_score_v2_summary.json" \
  --out-markdown "${OUT_DIR}/comparison.md"

echo "\nDone. Output directory: ${OUT_DIR}"
echo "- comparison: ${OUT_DIR}/comparison.md"
echo "- ask v2 summary: ${OUT_DIR}/vlm_ask_score_v2_summary.json"
echo "- chat v2 summary: ${OUT_DIR}/vlm_chat_score_v2_summary.json"
