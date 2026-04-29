#!/usr/bin/env bash
set -euo pipefail

IMAGE_PATH="${1:-/data/runtime_uploads/screen_500kb.png}"

declare -a CASES=(
  "ocr on"
  "ocr off"
  "vlm on"
  "vlm off"
)

for c in "${CASES[@]}"; do
  MODE="$(echo "$c" | awk '{print $1}')"
  RERANK="$(echo "$c" | awk '{print $2}')"

  echo "========================================"
  echo "[RUN] mode=${MODE}, reranker=${RERANK}"
  echo "========================================"

  scripts/perf/run_benchmark_case.sh "$MODE" "$RERANK" "$IMAGE_PATH"

  echo "[DONE] mode=${MODE}, reranker=${RERANK}"
  echo
done

echo "[OK] Matrix finished."
echo "[INFO] Latest results:"
ls -1dt data/rag_traces/runtime_stage_benchmark/* | head -n 20
