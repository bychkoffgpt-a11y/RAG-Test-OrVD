#!/usr/bin/env bash
set -euo pipefail

VISION_MODE="${1:-}"
RERANKER_MODE="${2:-}"

if [[ ! "$VISION_MODE" =~ ^(ocr|vlm)$ ]]; then
  echo "ERROR: VISION mode must be 'ocr' or 'vlm'"
  exit 1
fi
if [[ ! "$RERANKER_MODE" =~ ^(on|off)$ ]]; then
  echo "ERROR: reranker mode must be 'on' or 'off'"
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found in repo root"
  exit 1
fi

RERANKER_BOOL=true
[[ "$RERANKER_MODE" == "off" ]] && RERANKER_BOOL=false

upsert_env() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${val}|g" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

upsert_env "VISION_RUNTIME_MODE" "$VISION_MODE"
upsert_env "RETRIEVAL_USE_RERANKER" "$RERANKER_BOOL"

echo "[INFO] .env updated:"
grep -E '^(VISION_RUNTIME_MODE|RETRIEVAL_USE_RERANKER)=' .env

echo "[INFO] Recreate support-api..."
docker compose up -d --force-recreate support-api

echo "[INFO] Waiting for support-api readiness..."
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "[OK] support-api is ready"
    break
  fi
  sleep 1
done

if ! curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  echo "[ERROR] support-api is not ready after timeout"
  exit 1
fi

echo "[INFO] Effective env in container:"
docker compose exec support-api sh -lc 'printenv | grep -E "^(VISION_RUNTIME_MODE|RETRIEVAL_USE_RERANKER)="'
