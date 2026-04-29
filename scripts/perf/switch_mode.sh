#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/perf/switch_mode.sh <vision_mode> <reranker_mode>

Обновляет .env и перезапускает support-api для переключения режима vision и reranker.

Arguments:
  vision_mode      ocr | vlm
  reranker_mode    on  | off

Что делает скрипт:
  1) Проверяет входные аргументы и наличие .env.
  2) Устанавливает VISION_RUNTIME_MODE и RETRIEVAL_USE_RERANKER в .env.
  3) Пересоздаёт контейнер support-api.
  4) Ждёт readiness endpoint (/health) до 30 секунд.
  5) Показывает эффективные значения переменных в контейнере.

Examples:
  ./scripts/perf/switch_mode.sh ocr on
  ./scripts/perf/switch_mode.sh vlm off

Options:
  -h, --help      Показать эту справку и выйти.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

VISION_MODE="${1:-}"
RERANKER_MODE="${2:-}"

if [[ -z "$VISION_MODE" || -z "$RERANKER_MODE" ]]; then
  echo "ERROR: missing required arguments." >&2
  usage
  exit 1
fi

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
