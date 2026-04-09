#!/usr/bin/env bash
set -euo pipefail
MODE="offline"
FORCE_BUILD=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/update_app.sh [--mode offline|online] [--build]

Options:
  --mode MODE   Режим обновления:
                  offline (по умолчанию) — строгая проверка wheelhouse
                  online                — допускается пустой wheelhouse
  --offline     Эквивалент: --mode offline
  --online      Эквивалент: --mode online
  --build       Принудительная пересборка support-api, даже если входы образа не менялись
  -h, --help    Показать справку
USAGE
}

log() {
  echo "[INFO] $*"
}

ok() {
  echo "[OK] $*"
}

warn() {
  echo "[WARN] $*" >&2
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

should_rebuild_support_api() {
  local pre_head="$1"
  local post_head="$2"
  local mode="$3"

  if [[ "$FORCE_BUILD" -eq 1 ]]; then
    log "Включён --build: пересборка support-api будет выполнена принудительно"
    return 0
  fi

  local image_tag="csv-ans-support-bot-support-api:latest"
  if ! docker image inspect "$image_tag" >/dev/null 2>&1; then
    log "Локальный образ $image_tag не найден: требуется первичная сборка"
    return 0
  fi

  if [[ "$pre_head" == "$post_head" ]]; then
    log "Git-коммиты не изменились: пересборка support-api не требуется"
    return 1
  fi

  local changed_files
  changed_files="$(git diff --name-only "$pre_head" "$post_head")"

  if [[ -z "$changed_files" ]]; then
    log "Изменений в репозитории после pull не обнаружено"
    return 1
  fi

  if echo "$changed_files" | rg -q '^(app/Dockerfile|app/pyproject\.toml|app/src/|app/wheels/|docker-compose\.yml|\.env\.example)'; then
    log "Обнаружены изменения, влияющие на образ support-api: выполняю пересборку"
    return 0
  fi

  if [[ "$mode" == "offline" ]] && echo "$changed_files" | rg -q '^scripts/preflight_check\.sh$'; then
    log "Изменена логика preflight/offline-проверки: выполняю пересборку для консистентности"
    return 0
  fi

  log "Изменения не затрагивают входы образа support-api: пересборка не требуется"
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { usage; fail "Не указано значение для --mode"; }
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
    --build)
      FORCE_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "Неизвестный параметр: $1"
      ;;
  esac
done

case "$MODE" in
  offline|online) ;;
  *)
    fail "Некорректный режим MODE='$MODE'. Ожидается: offline или online"
    ;;
esac

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT_DIR" ]] || fail "Скрипт нужно запускать внутри Git-репозитория проекта."
cd "$ROOT_DIR"

require_cmd git
require_cmd docker
require_cmd rg

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

pre_pull_head="$(git rev-parse HEAD)"

log "Останавливаю приложение (docker compose down --remove-orphans)..."
docker compose down --remove-orphans
ok "Компоненты приложения остановлены"

log "Обновляю ссылки на удалённые ветки (git fetch --all --prune)..."
git fetch --all --prune
ok "fetch завершён"

log "Подтягиваю обновления текущей ветки fast-forward (git pull --ff-only)..."
git pull --ff-only
ok "pull завершён"

post_pull_head="$(git rev-parse HEAD)"

if [[ -x "./scripts/preflight_check.sh" ]]; then
  log "Запускаю предпусковую проверку (режим: $MODE)..."
  ./scripts/preflight_check.sh --mode "$MODE"
  ok "Предпусковая проверка пройдена"
else
  warn "preflight_check.sh не найден/не исполняемый, пропускаю проверку"
fi

if should_rebuild_support_api "$pre_pull_head" "$post_pull_head" "$MODE"; then
  log "Запускаю приложение (docker compose up -d --build, PIP_MODE=$MODE)..."
  PIP_MODE="$MODE" docker compose up -d --build
else
  log "Запускаю приложение без пересборки образа (docker compose up -d)..."
  docker compose up -d
fi

ok "Приложение запущено"
log "Готово: стек обновлён и перезапущен."
