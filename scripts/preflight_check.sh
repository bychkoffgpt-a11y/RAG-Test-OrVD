#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
SKIP_DOCKER_CHECK=0

if [[ "${1:-}" == "--skip-docker" ]]; then
  SKIP_DOCKER_CHECK=1
fi

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

warn() {
  echo "[WARN] $*" >&2
}

ok() {
  echo "[OK] $*"
}

require_file() {
  local f="$1"
  [[ -f "$f" ]] || fail "Файл не найден: $f"
  ok "Найден файл: $f"
}

require_nonempty_var() {
  local key="$1"
  local val="${!key:-}"
  [[ -n "$val" ]] || fail "В .env не задана переменная: $key"
}

require_not_placeholder() {
  local key="$1"
  local val="${!key:-}"
  local placeholder="$2"
  [[ "$val" != "$placeholder" ]] || fail "В .env переменная $key содержит небезопасный placeholder '$placeholder'"
}

require_dir() {
  local d="$1"
  [[ -d "$d" ]] || fail "Каталог не найден: $d"
  ok "Найден каталог: $d"
}

require_model_file() {
  local file="$1"
  [[ -f "$file" ]] || fail "Файл модели не найден: $file"
  ok "Найден файл модели: $file"
}

require_compose_env_refs() {
  local key="$1"
  local pattern="\\$\\{${key}([:-][^}]*)?}"

  if command -v rg >/dev/null 2>&1; then
    rg -n "$pattern" "$COMPOSE_FILE" >/dev/null \
      || warn "Переменная $key не используется в docker-compose.yml"
    return
  fi

  grep -nE "$pattern" "$COMPOSE_FILE" >/dev/null \
    || warn "Переменная $key не используется в docker-compose.yml (подсказка: установите ripgrep для более точной проверки)"
}

check_docker_image_tag() {
  local image="$1"
  if [[ "$SKIP_DOCKER_CHECK" -eq 1 ]]; then
    warn "Проверка pull образа пропущена (--skip-docker): $image"
    return 0
  fi

  command -v docker >/dev/null || fail "Команда docker не найдена в PATH"
  ok "Docker CLI доступен"

  docker pull "$image" >/dev/null
  ok "Образ доступен: $image"
}

require_file "$ENV_FILE"
require_file "$COMPOSE_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD WEBUI_SECRET_KEY WEBUI_API_KEY GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD LLM_MODEL_FILE; do
  require_nonempty_var "$key"
  require_compose_env_refs "$key"
done

require_not_placeholder POSTGRES_PASSWORD change_me_strong
require_not_placeholder WEBUI_SECRET_KEY change_me_secret
require_not_placeholder GRAFANA_ADMIN_PASSWORD change_me_grafana

require_dir "$ROOT_DIR/models"
require_dir "$ROOT_DIR/models/llm"
require_dir "$ROOT_DIR/models/embeddings"
require_dir "$ROOT_DIR/models/reranker"
require_dir "$ROOT_DIR/data/inbox/csv_ans_docs"
require_dir "$ROOT_DIR/data/inbox/internal_regulations"

require_model_file "$ROOT_DIR/models/llm/${LLM_MODEL_FILE}"
require_model_file "$ROOT_DIR/models/embeddings/bge-m3/config.json"
require_model_file "$ROOT_DIR/models/reranker/bge-reranker-v2-m3/config.json"

LLAMA_CPP_IMAGE="${LLAMA_CPP_IMAGE:-ghcr.io/ggerganov/llama.cpp:server-cuda-b4719}"
check_docker_image_tag "$LLAMA_CPP_IMAGE"

if [[ "$SKIP_DOCKER_CHECK" -eq 0 ]]; then
  docker compose -f "$COMPOSE_FILE" config >/dev/null
  ok "docker compose config проходит валидацию"
else
  warn "Валидация docker compose config пропущена из-за --skip-docker"
fi

ok "Preflight проверка завершена успешно"
