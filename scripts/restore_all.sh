#!/usr/bin/env bash
set -euo pipefail
MODE="offline"
BKP=""

usage() {
  echo "Usage: $0 [--mode offline|online] <backup_dir>"
}

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
      usage
      exit 0
      ;;
    -*)
      echo "[FAIL] Неизвестный параметр: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -z "$BKP" ]]; then
        BKP="$1"
      else
        echo "[FAIL] Указано больше одного backup_dir: '$BKP' и '$1'" >&2
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

case "$MODE" in
  offline|online) ;;
  *) echo "[FAIL] Некорректный режим: $MODE" >&2; exit 1 ;;
esac

if [[ -z "$BKP" ]]; then
  usage
  exit 1
fi

test -d "$BKP" || { echo "Backup dir not found"; exit 1; }

docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$BKP/postgres.sql"
cp -r "$BKP"/inbox data/
cp -r "$BKP"/processed data/
cp -r "$BKP"/assets data/
echo "Restore completed (mode=$MODE) from $BKP"
