#!/usr/bin/env bash
set -euo pipefail
MODE="offline"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "[FAIL] Не указано значение для --mode" >&2; exit 1; }
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
      echo "Usage: ./scripts/reindex_b.sh [--mode offline|online]"
      exit 0
      ;;
    *)
      echo "[FAIL] Неизвестный параметр: $1" >&2
      exit 1
      ;;
  esac
done

case "$MODE" in
  offline|online) ;;
  *) echo "[FAIL] Некорректный режим: $MODE" >&2; exit 1 ;;
esac

echo "[INFO] reindex_b режим: $MODE"
docker compose run --rm ingest-b
