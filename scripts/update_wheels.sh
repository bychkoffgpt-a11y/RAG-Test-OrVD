#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
PYPROJECT_FILE="${APP_DIR}/pyproject.toml"
WHEELS_DIR="${APP_DIR}/wheels"
MODE="refresh"
INCLUDE_DEV=0
STRICT=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/update_wheels.sh [--mode refresh|append] [--include-dev] [--strict]

Скрипт безопасно обновляет wheelhouse в app/wheels:
  - refresh (по умолчанию): пересоздаёт wheelhouse атомарно через временный каталог
  - append: докачивает недостающие wheel в существующий каталог

Options:
  --mode MODE    refresh|append
  --include-dev  добавить зависимости из project.optional-dependencies.dev
  --strict       завершиться с ошибкой, если wheelhouse неполный/несовместимый
  -h, --help     Показать справку
USAGE
}

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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { usage; fail "Не указано значение для --mode"; }
      MODE="$2"
      shift 2
      ;;
    --include-dev)
      INCLUDE_DEV=1
      shift
      ;;
    --strict)
      STRICT=1
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
  refresh|append) ;;
  *) fail "Некорректный режим MODE='$MODE'. Ожидается: refresh или append" ;;
esac

require_cmd python3

[[ -f "$PYPROJECT_FILE" ]] || fail "Файл не найден: $PYPROJECT_FILE"
mkdir -p "$WHEELS_DIR"

req_file="$(mktemp)"
trap 'rm -f "$req_file"' EXIT

log "Извлекаю список зависимостей из $PYPROJECT_FILE..."
python3 - "$PYPROJECT_FILE" "$req_file" "$INCLUDE_DEV" <<'PY'
import pathlib
import sys
import tomllib

pyproject_path = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
include_dev = bool(int(sys.argv[3]))
with pyproject_path.open('rb') as fh:
    data = tomllib.load(fh)

requirements = []
requirements.extend(data.get('project', {}).get('dependencies', []))
requirements.extend(data.get('build-system', {}).get('requires', []))
if include_dev:
    requirements.extend(data.get('project', {}).get('optional-dependencies', {}).get('dev', []))

seen = set()
ordered_unique = []
for req in requirements:
    if req not in seen:
        ordered_unique.append(req)
        seen.add(req)

out_path.write_text('\n'.join(ordered_unique) + '\n', encoding='utf-8')
PY

validate_wheelhouse() {
  local wheel_dir="$1"
  local tmp_validate_dir
  tmp_validate_dir="$(mktemp -d)"
  if ! python3 -m pip download \
    --disable-pip-version-check \
    --dest "$tmp_validate_dir" \
    --no-index \
    --find-links "$wheel_dir" \
    -r "$req_file" >/dev/null; then
    rm -rf "$tmp_validate_dir"
    return 1
  fi
  rm -rf "$tmp_validate_dir"
}

if [[ "$MODE" == "append" ]]; then
  log "Режим append: докачиваю недостающие wheels в $WHEELS_DIR..."
  python3 -m pip download \
    --disable-pip-version-check \
    --retries 10 \
    --dest "$WHEELS_DIR" \
    -r "$req_file"

  log "Проверяю полноту wheelhouse (прямые и транзитивные зависимости)..."
  if ! validate_wheelhouse "$WHEELS_DIR"; then
    if [[ "$STRICT" -eq 1 ]]; then
      fail "После append wheelhouse всё ещё неполный или несовместимый: $WHEELS_DIR"
    fi
    log "Wheelhouse после append остаётся неполным/несовместимым (strict отключён)"
  else
    ok "Полнота wheelhouse подтверждена (append)"
  fi
  ok "Wheelhouse успешно обновлён (append): $WHEELS_DIR"
  exit 0
fi

tmp_wheels_dir="$(mktemp -d)"
backup_dir="${WHEELS_DIR}.bak.$(date +%Y%m%d%H%M%S)"
cleanup_tmp() {
  rm -rf "$tmp_wheels_dir"
}
trap 'cleanup_tmp; rm -f "$req_file"' EXIT

log "Режим refresh: формирую новый wheelhouse во временном каталоге..."
python3 -m pip download \
  --disable-pip-version-check \
  --retries 10 \
  --dest "$tmp_wheels_dir" \
  -r "$req_file"

log "Проверяю полноту нового wheelhouse (прямые и транзитивные зависимости)..."
if ! validate_wheelhouse "$tmp_wheels_dir"; then
  if [[ "$STRICT" -eq 1 ]]; then
    fail "Скачанный wheelhouse неполный или несовместимый. Текущий $WHEELS_DIR не изменён."
  fi
  log "Скачанный wheelhouse неполный/несовместимый (strict отключён), но каталог будет обновлён."
else
  ok "Полнота нового wheelhouse подтверждена (прямые и транзитивные зависимости)"
fi

if [[ -d "$WHEELS_DIR" ]]; then
  mv "$WHEELS_DIR" "$backup_dir"
  log "Текущий wheelhouse сохранён в резервную копию: $backup_dir"
fi

if ! mv "$tmp_wheels_dir" "$WHEELS_DIR"; then
  if [[ -d "$backup_dir" ]]; then
    mv "$backup_dir" "$WHEELS_DIR" || true
  fi
  fail "Не удалось атомарно заменить wheelhouse. Выполнен откат (если возможно)."
fi

if [[ -d "$backup_dir" ]]; then
  rm -rf "$backup_dir"
fi

# Сохраняем служебный файл для пустого каталога в git.
# Файл .gitkeep не влияет на установку wheel, но нужен для отслеживания директории.
touch "${WHEELS_DIR}/.gitkeep"

ok "Wheelhouse успешно пересобран и проверен: $WHEELS_DIR"
