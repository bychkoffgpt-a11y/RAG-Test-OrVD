#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
PYPROJECT_FILE="${APP_DIR}/pyproject.toml"
WHEELS_DIR="${APP_DIR}/wheels"
MODE="refresh"
INCLUDE_DEV=0
STRICT=0
PIP_RETRIES="${PIP_RETRIES:-12}"
PIP_TIMEOUT="${PIP_TIMEOUT:-60}"

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
  Переменные окружения:
    PIP_RETRIES  количество retries для pip (по умолчанию: 12)
    PIP_TIMEOUT  таймаут HTTP-запроса pip в секундах (по умолчанию: 60)
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

extract_unreachable_endpoints() {
  local log_file="$1"
  python3 - "$log_file" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")

patterns = [
    re.compile(r"HTTPSConnectionPool\(host='([^']+)', port=(\d+)\)"),
    re.compile(r"Could not fetch URL (\S+):"),
    re.compile(r"Failed to establish a new connection: \[Errno [^]]+\] [^:]+: '([^']+)'"),
]

matches = set()
for pattern in patterns:
    for hit in pattern.findall(text):
        if isinstance(hit, tuple):
            matches.add(f"{hit[0]}:{hit[1]}")
        else:
            matches.add(hit.rstrip(".,;"))

if matches:
    print(", ".join(sorted(matches)))
PY
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

preflight_check_available_versions() {
  local report_file
  local preflight_err_log
  report_file="$(mktemp)"
  preflight_err_log="$(mktemp)"
  if ! python3 -m pip install \
    --dry-run \
    --ignore-installed \
    --disable-pip-version-check \
    --retries "$PIP_RETRIES" \
    --timeout "$PIP_TIMEOUT" \
    --report "$report_file" \
    -r "$req_file" >/dev/null 2>"$preflight_err_log"; then
    local endpoints
    endpoints="$(extract_unreachable_endpoints "$preflight_err_log" || true)"
    rm -f "$preflight_err_log"
    rm -f "$report_file"
    if [[ -n "$endpoints" ]]; then
      fail "Предварительная проверка зависимостей не пройдена: не удалось подключиться к ${endpoints} (retries=${PIP_RETRIES}, timeout=${PIP_TIMEOUT}s)."
    fi
    return 1
  fi
  rm -f "$preflight_err_log"

  # sanity-check: в отчёте должны быть запланированные установки
  if ! python3 - "$report_file" <<'PY'
import json
import pathlib
import sys

report_path = pathlib.Path(sys.argv[1])
payload = json.loads(report_path.read_text(encoding="utf-8"))
items = payload.get("install", [])
if not items:
    raise SystemExit(1)
PY
  then
    rm -f "$report_file"
    return 1
  fi

  rm -f "$report_file"
}

log "Проверяю доступность требуемых версий (включая транзитивные зависимости) до загрузки wheelhouse..."
if ! preflight_check_available_versions; then
  fail "Предварительная проверка зависимостей не пройдена: часть версий недоступна или индекс недостижим (retries=${PIP_RETRIES}, timeout=${PIP_TIMEOUT}s)."
fi
ok "Предварительная проверка зависимостей пройдена"

if [[ "$MODE" == "append" ]]; then
  log "Режим append: докачиваю недостающие wheels в $WHEELS_DIR..."
  python3 -m pip download \
    --disable-pip-version-check \
    --retries "$PIP_RETRIES" \
    --timeout "$PIP_TIMEOUT" \
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
  --retries "$PIP_RETRIES" \
  --timeout "$PIP_TIMEOUT" \
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
