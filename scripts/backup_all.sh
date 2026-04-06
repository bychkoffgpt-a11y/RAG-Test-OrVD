#!/usr/bin/env bash
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p data/backups/$TS
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > data/backups/$TS/postgres.sql
cp -r data/inbox data/processed data/assets data/backups/$TS/
echo "Backup completed: data/backups/$TS"
