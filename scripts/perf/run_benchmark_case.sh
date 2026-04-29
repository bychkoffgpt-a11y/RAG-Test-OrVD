#!/usr/bin/env bash
set -euo pipefail

VISION_MODE="${1:-ocr}"
RERANKER_MODE="${2:-on}"
IMAGE_PATH="${3:-/data/runtime_uploads/screen_500kb.png}"

scripts/perf/switch_mode.sh "$VISION_MODE" "$RERANKER_MODE"

python3 scripts/run_runtime_stage_benchmark.py \
  --api-url http://localhost:8000 \
  --question "Добрый день. В программе СВР АНС филиала Аэронавигация Юга по-прежнему не входит ставка сбора за 11.02.2026! Отработаны все возможные операции в программе со стороны филиала. Публикация за январь и февраль, Перепроверить в полетах. За 12.02.2026 все ставки стоят благополучно. Что с 11.02.2026?" \
  --image-path "$IMAGE_PATH" \
  --top-k 6 \
  --iterations 8 \
  --adaptive \
  --mode-hint "$VISION_MODE" \
  --reranker-hint "$RERANKER_MODE"
