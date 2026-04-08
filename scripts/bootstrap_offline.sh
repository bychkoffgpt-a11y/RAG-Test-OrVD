#!/usr/bin/env bash
set -euo pipefail
MODE="offline"

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap_offline.sh [--mode offline|online]

Options:
  --mode MODE   Режим инициализации (offline|online), по умолчанию offline
  --offline     Эквивалент: --mode offline
  --online      Эквивалент: --mode online
  -h, --help    Показать справку
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { usage; echo "[FAIL] Не указано значение для --mode" >&2; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --offline)
      MODE="offline"
      shift
      ;;
    --online)
      MODE="online"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      echo "[FAIL] Неизвестный параметр: $1" >&2
      exit 1
      ;;
  esac
done

case "$MODE" in
  offline|online) ;;
  *)
    echo "[FAIL] Некорректный режим MODE='$MODE'. Ожидается: offline или online" >&2
    exit 1
    ;;
esac

cp -n .env.example .env || true
mkdir -p data/inbox/csv_ans_docs data/inbox/internal_regulations data/processed/csv_ans_docs data/processed/internal_regulations data/assets/images data/backups
mkdir -p models/llm models/embeddings models/reranker

echo "[OK] Базовая структура подготовлена."
echo "[INFO] Режим инициализации: $MODE"
echo "[INFO] Заполните .env и поместите модели в models/ согласно docs/model_registry.md."
