#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup_dir>"
  exit 1
fi
BKP="$1"

test -d "$BKP" || { echo "Backup dir not found"; exit 1; }

docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$BKP/postgres.sql"
cp -r "$BKP"/inbox data/
cp -r "$BKP"/processed data/
cp -r "$BKP"/assets data/
echo "Restore completed from $BKP"
