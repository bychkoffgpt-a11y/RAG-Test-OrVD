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
      echo "Usage: ./scripts/backup_all.sh [--mode offline|online]"
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

TS=$(date +%Y%m%d_%H%M%S)
mkdir -p data/backups/$TS
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > data/backups/$TS/postgres.sql
cp -r data/inbox data/processed data/assets data/backups/$TS/
echo "Backup completed (mode=$MODE): data/backups/$TS"
