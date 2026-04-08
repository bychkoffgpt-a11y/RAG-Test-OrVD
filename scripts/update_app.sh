#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[INFO] $*"
}

ok() {
  echo "[OK] $*"
}

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Команда не найдена: $1"
}

require_clean_git_tree() {
  if ! git diff --quiet --ignore-submodules --; then
    fail "Есть незакоммиченные изменения (working tree). Зафиксируйте или сохраните их перед обновлением."
  fi

  if ! git diff --cached --quiet --ignore-submodules --; then
    fail "Есть изменения в индексе (staged). Зафиксируйте их перед обновлением."
  fi
}

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT_DIR" ]] || fail "Скрипт нужно запускать внутри Git-репозитория проекта."
cd "$ROOT_DIR"

require_cmd git
require_cmd docker

if [[ ! -f "docker-compose.yml" ]]; then
  fail "В корне проекта не найден docker-compose.yml"
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "Текущий каталог не является рабочим деревом Git"
fi

current_branch="$(git symbolic-ref --short -q HEAD || true)"
[[ -n "$current_branch" ]] || fail "detached HEAD: переключитесь на ветку перед обновлением."

upstream_ref="$(git rev-parse --abbrev-ref --symbolic-full-name "${current_branch}@{upstream}" 2>/dev/null || true)"
[[ -n "$upstream_ref" ]] || fail "Для ветки '$current_branch' не настроен upstream. Выполните: git branch --set-upstream-to origin/$current_branch"

require_clean_git_tree

log "Обновляю ссылки на удалённые ветки (git fetch --all --prune)..."
git fetch --all --prune
ok "fetch завершён"

log "Подтягиваю обновления текущей ветки fast-forward (git pull --ff-only)..."
git pull --ff-only
ok "pull завершён"

if [[ -x "./scripts/preflight_check.sh" ]]; then
  log "Запускаю предпусковую проверку..."
  ./scripts/preflight_check.sh
  ok "Предпусковая проверка пройдена"
else
  log "preflight_check.sh не найден/не исполняемый, пропускаю проверку"
fi

log "Останавливаю приложение (docker compose down --remove-orphans)..."
docker compose down --remove-orphans
ok "Компоненты приложения остановлены"

log "Запускаю приложение (docker compose up -d --build)..."
docker compose up -d --build
ok "Приложение запущено"

log "Готово: стек обновлён и перезапущен."
