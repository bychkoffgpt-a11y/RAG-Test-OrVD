#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/perf/run_benchmark_case.sh [vision_mode] [reranker_mode] [image_path]

Запускает единичный benchmark-кейс runtime RAG-stage после переключения режима.

Arguments (optional):
  vision_mode      ocr | vlm (default: ocr)
  reranker_mode    on  | off (default: on)
  image_path       Путь к изображению внутри контейнера support-api
                   (default: /data/runtime_uploads/screen_500kb.png)

Что делает скрипт:
  1) Вызывает ./scripts/perf/switch_mode.sh для переключения режима.
  2) Запускает scripts/run_runtime_stage_benchmark.py с фиксированным
     enterprise-вопросом и параметрами top_k/iterations/adaptive.

Examples:
  ./scripts/perf/run_benchmark_case.sh
  ./scripts/perf/run_benchmark_case.sh vlm on /data/runtime_uploads/screen_1mb.png

Options:
  -h, --help      Показать эту справку и выйти.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

VISION_MODE="${1:-ocr}"
RERANKER_MODE="${2:-on}"
IMAGE_PATH="${3:-/data/runtime_uploads/screen_500kb.png}"

scripts/perf/switch_mode.sh "$VISION_MODE" "$RERANKER_MODE"

python3 scripts/run_runtime_stage_benchmark.py   --api-url http://localhost:8000   --question "Добрый день. В программе СВР АНС филиала Аэронавигация Юга по-прежнему не входит ставка сбора за 11.02.2026! Отработаны все возможные операции в программе со стороны филиала. Публикация за январь и февраль, Перепроверить в полетах. За 12.02.2026 все ставки стоят благополучно. Что с 11.02.2026?"   --image-path "$IMAGE_PATH"   --top-k 6   --iterations 8   --adaptive   --mode-hint "$VISION_MODE"   --reranker-hint "$RERANKER_MODE"
