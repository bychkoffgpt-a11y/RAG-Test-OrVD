#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/perf/run_matrix.sh [image_path]

Запускает матрицу из 4 benchmark-кейсов:
  1) ocr + reranker on
  2) ocr + reranker off
  3) vlm + reranker on
  4) vlm + reranker off

Argument:
  image_path       Путь к тестовому изображению внутри контейнера
                   (default: /data/runtime_uploads/screen_500kb.png)

Скрипт последовательно вызывает:
  ./scripts/perf/run_benchmark_case.sh <mode> <reranker> <image_path>

Examples:
  ./scripts/perf/run_matrix.sh
  ./scripts/perf/run_matrix.sh /data/runtime_uploads/screen_1mb.png

Options:
  -h, --help      Показать эту справку и выйти.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

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
