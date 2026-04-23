#!/usr/bin/env bash
set -euo pipefail
MODE="offline"
FORCE_BUILD=0
ONLINE_STRICT_WHEELS=0
FILES_ONLY=0
YC_DOCKER_AUTH="${YC_DOCKER_AUTH:-auto}"
PIP_INDEX_URL_VALUE="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_FALLBACK_INDEX_URL_VALUE="${PIP_FALLBACK_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
DEBIAN_MIRROR_VALUE="${DEBIAN_MIRROR:-https://mirror.yandex.ru/debian}"
DEBIAN_SECURITY_MIRROR_VALUE="${DEBIAN_SECURITY_MIRROR:-https://mirror.yandex.ru/debian-security}"

usage() {
  cat <<'USAGE'
Usage: ./scripts/update_app.sh [--mode offline|online] [--build] [--files-only] [--online-strict-wheels|--allow-pypi-fallback]

Options:
  --mode MODE   Режим обновления:
                  offline (по умолчанию) — строгая проверка wheelhouse
                  online                — допускается пустой wheelhouse
  --offline     Эквивалент: --mode offline
  --online      Эквивалент: --mode online
  --build       Принудительная пересборка support-api, даже если входы образа не менялись
  --files-only  Только безопасно обновить файлы из Git (fetch + pull), без остановки, пересборки и перезапуска контейнеров
  --online-strict-wheels
                В режиме online требовать полный wheelhouse и отключать fallback на PyPI
  --allow-pypi-fallback
                Явно разрешить fallback на PyPI в режиме online (по умолчанию)
  -h, --help    Показать справку

Environment:
  YC_DOCKER_AUTH=auto|0|1
                Авто-настройка Docker auth для cr.yandex/* через yc:
                  auto (по умолчанию) — только когда в compose есть cr.yandex/*
                  1                  — всегда пытаться настроить yc auth
                  0                  — отключить авто-настройку
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

compose_uses_yandex_registry() {
  local images
  images="$(docker compose config --images 2>/dev/null || true)"
  [[ -n "$images" ]] || return 1
  if echo "$images" | rg -q '^cr\.yandex/'; then
    return 0
  fi
  return 1
}

ensure_yandex_registry_auth() {
  local should_configure=0
  case "$YC_DOCKER_AUTH" in
    1) should_configure=1 ;;
    0) should_configure=0 ;;
    auto)
      if compose_uses_yandex_registry; then
        should_configure=1
      fi
      ;;
    *)
      warn "Неизвестное значение YC_DOCKER_AUTH=${YC_DOCKER_AUTH}. Использую auto."
      if compose_uses_yandex_registry; then
        should_configure=1
      fi
      ;;
  esac

  if [[ "$should_configure" -ne 1 ]]; then
    log "Пропускаю авто-настройку yc docker auth (YC_DOCKER_AUTH=${YC_DOCKER_AUTH})"
    return 0
  fi

  if ! command -v yc >/dev/null 2>&1; then
    warn "yc CLI не найден. Выполните авторизацию вручную: 'yc init' и 'yc container registry configure-docker'"
    return 0
  fi

  log "Настраиваю Docker auth для Yandex Container Registry (yc container registry configure-docker)..."
  if yc container registry configure-docker >/dev/null; then
    ok "Docker auth для cr.yandex настроен"
  else
    warn "Не удалось выполнить yc container registry configure-docker. Продолжаю, но pull/build может завершиться ошибкой доступа."
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
    --files-only)
      FILES_ONLY=1
      shift
      ;;
    --online-strict-wheels)
      ONLINE_STRICT_WHEELS=1
      shift
      ;;
    --allow-pypi-fallback)
      ONLINE_STRICT_WHEELS=0
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

if [[ "$FILES_ONLY" -eq 1 && "$FORCE_BUILD" -eq 1 ]]; then
  fail "Параметры --files-only и --build несовместимы"
fi

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$ROOT_DIR" ]] || fail "Скрипт нужно запускать внутри Git-репозитория проекта."
cd "$ROOT_DIR"

require_cmd git
require_cmd rg
if [[ "$FILES_ONLY" -ne 1 ]]; then
  require_cmd docker
  mkdir -p "$ROOT_DIR/.docker-cache/support-api" "$ROOT_DIR/.docker-cache/ingest"
fi

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

log "Обновляю ссылки на удалённые ветки (git fetch --all --prune)..."
git fetch --all --prune
ok "fetch завершён"

log "Подтягиваю обновления текущей ветки fast-forward (git pull --ff-only)..."
git pull --ff-only
ok "pull завершён"

post_pull_head="$(git rev-parse HEAD)"

if [[ "$FILES_ONLY" -eq 1 ]]; then
  ok "Файлы проекта безопасно обновлены без управления контейнерами (--files-only)"
  log "Готово: выполнены только git fetch/git pull."
  exit 0
fi

log "Останавливаю приложение (docker compose down --remove-orphans)..."
docker compose down --remove-orphans
ok "Компоненты приложения остановлены"

if [[ -x "./scripts/preflight_check.sh" ]]; then
  log "Запускаю предпусковую проверку (режим: $MODE)..."
  preflight_args=(--mode "$MODE")
  if [[ "$MODE" == "online" && "$ONLINE_STRICT_WHEELS" -eq 1 ]]; then
    preflight_args+=(--online-strict-wheels)
  fi
  ./scripts/preflight_check.sh "${preflight_args[@]}"
  ok "Предпусковая проверка пройдена"
else
  warn "preflight_check.sh не найден/не исполняемый, пропускаю проверку"
fi

ensure_yandex_registry_auth

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

if should_rebuild_support_api "$pre_pull_head" "$post_pull_head" "$MODE"; then
  log "Запускаю приложение (docker compose up -d --build, PIP_MODE=$MODE, ONLINE_STRICT_WHEELS=$ONLINE_STRICT_WHEELS)..."
  log "Индексы pip: primary=${PIP_INDEX_URL_VALUE}, mirror=${PIP_FALLBACK_INDEX_URL_VALUE}"
  log "Зеркала Debian: main=${DEBIAN_MIRROR_VALUE}, security=${DEBIAN_SECURITY_MIRROR_VALUE}"
  if [[ "$MODE" == "online" && "$ONLINE_STRICT_WHEELS" -eq 1 ]]; then
    PIP_MODE="$MODE" \
      PIP_ONLINE_FALLBACK=0 \
      PIP_INDEX_URL="$PIP_INDEX_URL_VALUE" \
      PIP_FALLBACK_INDEX_URL="$PIP_FALLBACK_INDEX_URL_VALUE" \
      DEBIAN_MIRROR="$DEBIAN_MIRROR_VALUE" \
      DEBIAN_SECURITY_MIRROR="$DEBIAN_SECURITY_MIRROR_VALUE" \
      docker compose up -d --build
  else
    PIP_MODE="$MODE" \
      PIP_ONLINE_FALLBACK=1 \
      PIP_INDEX_URL="$PIP_INDEX_URL_VALUE" \
      PIP_FALLBACK_INDEX_URL="$PIP_FALLBACK_INDEX_URL_VALUE" \
      DEBIAN_MIRROR="$DEBIAN_MIRROR_VALUE" \
      DEBIAN_SECURITY_MIRROR="$DEBIAN_SECURITY_MIRROR_VALUE" \
      docker compose up -d --build
  fi
else
  log "Запускаю приложение без пересборки образа (docker compose up -d)..."
  docker compose up -d
fi

ok "Приложение запущено"
log "Готово: стек обновлён и перезапущен."
