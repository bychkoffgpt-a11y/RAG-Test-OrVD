#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true
mkdir -p data/inbox/csv_ans_docs data/inbox/internal_regulations data/processed/csv_ans_docs data/processed/internal_regulations data/assets/images data/backups
mkdir -p models/llm models/embeddings models/reranker

echo "[OK] Базовая структура подготовлена."
echo "[INFO] Заполните .env и поместите модели в models/."
