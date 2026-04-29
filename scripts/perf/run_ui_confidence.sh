#!/usr/bin/env bash
set -euo pipefail

# ===== Required env =====
: "${QUESTION:?set QUESTION}"
: "${WEBUI_BEARER_TOKEN:?set WEBUI_BEARER_TOKEN}"

# ===== Optional env with sane defaults =====
API_URL="${API_URL:-http://localhost:8000}"
WEBUI_URL="${WEBUI_URL:-http://localhost:3000}"
MODEL_ID="${MODEL_ID:-local-rag-model}"

ITER="${ITER:-30}"
WARMUP_ITER="${WARMUP_ITER:-8}"
SLEEP_SEC="${SLEEP_SEC:-0.4}"
TOP_K="${TOP_K:-6}"
SCOPE="${SCOPE:-all}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-512}"
IMAGE_PATH="${IMAGE_PATH:-/data/runtime_uploads/screen_500kb.png}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE_DIR="data/rag_traces/ui_overhead/confidence_${STAMP}"
mkdir -p "${BASE_DIR}"

run_case () {
  local text_only="$1"   # 1 or 0
  local tag="$2"         # text or multimodal

  echo "===== CASE: ${tag} (TEXT_ONLY=${text_only}) ====="
  export TEXT_ONLY="${text_only}"

  DIRECT_DIR="${BASE_DIR}/ask_direct_${tag}"
  WEBUI_DIR="${BASE_DIR}/openwebui_${tag}"

  scripts/perf/bench_ask_direct.sh "${DIRECT_DIR}"
  scripts/perf/bench_openwebui.sh "${WEBUI_DIR}"
  scripts/perf/compare_ui_overhead.sh \
    "${DIRECT_DIR}/summary.json" \
    "${WEBUI_DIR}/summary.json" | tee "${BASE_DIR}/compare_${tag}.txt"
}

# 1) Text-only
run_case 1 "text"

# 2) Multimodal
run_case 0 "multimodal"

echo "[OK] done: ${BASE_DIR}"