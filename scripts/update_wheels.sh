#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
PYPROJECT_FILE="${APP_DIR}/pyproject.toml"
WHEELS_DIR="${APP_DIR}/wheels"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT_DIR}/.env" && set +a
fi

MODE="refresh"
INCLUDE_DEV=0
STRICT=0
PIP_RETRIES="${PIP_RETRIES:-12}"
PIP_TIMEOUT="${PIP_TIMEOUT:-60}"
TARGET_PLATFORM="${TARGET_PLATFORM:-manylinux2014_x86_64}"
TARGET_PYTHON_VERSION="${TARGET_PYTHON_VERSION:-311}"
TARGET_IMPLEMENTATION="${TARGET_IMPLEMENTATION:-cp}"
TARGET_ABI="${TARGET_ABI:-cp311}"
PYTORCH_CUDA_INDEX_URL="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
TORCH_VERSION="${TORCH_VERSION:-2.10.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.25.0}"
TORCHAUDIO_VERSION="${TORCHAUDIO_VERSION:-2.10.0}"
# Дополнительные пакеты, которые ставятся в Dockerfile отдельными шагами
# и должны быть синхронизированы с локальным wheelhouse.
EXTRA_REQUIREMENTS=(
  "opencv-contrib-python-headless==4.10.0.84"
  "torch==${TORCH_VERSION}"
  "torchvision==${TORCHVISION_VERSION}"
  "torchaudio==${TORCHAUDIO_VERSION}"
)

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
    TARGET_PLATFORM          целевая платформа wheel (по умолчанию: manylinux2014_x86_64)
    TARGET_PYTHON_VERSION    целевая версия Python для wheel (по умолчанию: 311)
    TARGET_IMPLEMENTATION    python implementation (по умолчанию: cp)
    TARGET_ABI               ABI для wheel (по умолчанию: cp311)
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

format_duration() {
  local total_seconds="$1"
  local hours=$((total_seconds / 3600))
  local minutes=$(((total_seconds % 3600) / 60))
  local seconds=$((total_seconds % 60))
  printf "%02d:%02d:%02d" "$hours" "$minutes" "$seconds"
}

run_step() {
  local title="$1"
  shift

  local started_at
  started_at="$(date +%s)"
  local stdin_tmp=""
  echo
  echo "[STEP] ${title}"
  echo "[STEP] Команда: $*"

  # Если команда передана с heredoc (stdin не tty), сохраняем stdin во временный файл.
  # Иначе при фоне ("&") bash может подменить stdin на /dev/null.
  if [[ ! -t 0 ]]; then
    stdin_tmp="$(mktemp)"
    cat >"$stdin_tmp"
  fi

  if [[ -n "$stdin_tmp" ]]; then
    "$@" <"$stdin_tmp" &
  else
    "$@" &
  fi
  local cmd_pid=$!

  while kill -0 "$cmd_pid" 2>/dev/null; do
    local now elapsed
    now="$(date +%s)"
    elapsed=$((now - started_at))
    printf "\r[TIMER] %-72s %s" "${title}" "$(format_duration "$elapsed")"
    sleep 1
  done

  wait "$cmd_pid"
  local status=$?
  local finished_at elapsed_total
  finished_at="$(date +%s)"
  elapsed_total=$((finished_at - started_at))
  printf "\r[TIMER] %-72s %s\n" "${title}" "$(format_duration "$elapsed_total")"

  if [[ "$status" -ne 0 ]]; then
    [[ -n "$stdin_tmp" ]] && rm -f "$stdin_tmp"
    fail "Шаг завершился с ошибкой (${status}): ${title}"
  fi
  [[ -n "$stdin_tmp" ]] && rm -f "$stdin_tmp"
  ok "Шаг завершён: ${title} ($(format_duration "$elapsed_total"))"
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

extract_download_failure_reason() {
  local err_log="$1"
  local endpoints
  endpoints="$(extract_unreachable_endpoints "$err_log" || true)"
  if [[ -n "$endpoints" ]]; then
    echo "не удалось подключиться к ${endpoints}"
    return
  fi

  local last_line
  last_line="$(tail -n 1 "$err_log" 2>/dev/null | sed 's/^\s*//; s/\s*$//')"
  if [[ -n "$last_line" ]]; then
    echo "$last_line"
    return
  fi
  echo "подробности см. в логе pip"
}

is_index_availability_error() {
  local err_log="$1"
  python3 - "$err_log" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
patterns = [
    r"HTTPSConnectionPool",
    r"ConnectionResetError",
    r"Connection refused",
    r"Temporary failure in name resolution",
    r"Failed to establish a new connection",
    r"Read timed out",
    r"ConnectTimeoutError",
    r"SSLError",
    r"ProxyError",
    r"too many 5\d\d error responses",
    r"HTTP error 5\d\d",
]

for pattern in patterns:
    if re.search(pattern, text, flags=re.IGNORECASE):
        print("1")
        raise SystemExit(0)
print("0")
PY
}

pip_download_with_index_fallback() {
  local phase="$1"
  local dest_dir="$2"
  shift 2

  local primary_index="${PIP_INDEX_URL:-}"
  local fallback_index="${PIP_FALLBACK_INDEX_URL:-}"
  local extra_index="${PIP_EXTRA_INDEX_URL:-}"
  local -a extra_args=()
  local -a primary_args=()
  local -a fallback_args=()
  local err_log
  err_log="$(mktemp)"

  if [[ -n "$extra_index" ]]; then
    extra_args+=(--extra-index-url "$extra_index")
  fi

  if [[ -n "$primary_index" ]]; then
    primary_args+=(--index-url "$primary_index")
  fi
  primary_args+=("${extra_args[@]}")

  if [[ -n "$fallback_index" ]]; then
    fallback_args+=(--index-url "$fallback_index")
  fi
  fallback_args+=("${extra_args[@]}")

  if python3 -m pip download \
    --disable-pip-version-check \
    --retries "$PIP_RETRIES" \
    --timeout "$PIP_TIMEOUT" \
    "${TARGET_DOWNLOAD_ARGS[@]}" \
    --dest "$dest_dir" \
    "${primary_args[@]}" \
    "$@" 2>"$err_log"; then
    rm -f "$err_log"
    log "${phase}: pip download успешно завершён через primary index (${primary_index:-<pip default index>})"
    return 0
  fi

  local primary_reason
  local availability_error
  primary_reason="$(extract_download_failure_reason "$err_log")"
  availability_error="$(is_index_availability_error "$err_log")"
  rm -f "$err_log"

  if [[ "$availability_error" -eq 1 && -n "$fallback_index" && "$fallback_index" != "$primary_index" ]]; then
    log "${phase}: primary index недоступен по сети/доступности (${primary_reason}); переключаюсь на fallback (${fallback_index})"
    err_log="$(mktemp)"
    if python3 -m pip download \
      --disable-pip-version-check \
      --retries "$PIP_RETRIES" \
      --timeout "$PIP_TIMEOUT" \
      "${TARGET_DOWNLOAD_ARGS[@]}" \
      --dest "$dest_dir" \
      "${fallback_args[@]}" \
      "$@" 2>"$err_log"; then
      rm -f "$err_log"
      log "${phase}: pip download успешно завершён через fallback index (${fallback_index})"
      return 0
    fi

    local fallback_reason
    fallback_reason="$(extract_download_failure_reason "$err_log")"
    rm -f "$err_log"
    log "${phase}: fallback index тоже не сработал (${fallback_reason})"
    return 1
  fi

  if [[ "$availability_error" -ne 1 ]]; then
    log "${phase}: fallback не используется, т.к. ошибка не относится к сети/доступности индекса (${primary_reason})"
  elif [[ -z "$fallback_index" ]]; then
    log "${phase}: fallback index не задан, повторная попытка не выполняется"
  else
    log "${phase}: fallback index совпадает с primary (${fallback_index}), повторная попытка не выполняется"
  fi
  log "${phase}: primary index не сработал (${primary_reason})"
  return 1
}

download_requirements_with_fallback() {
  local dest_dir="$1"
  local phase="$2"
  pip_download_with_index_fallback "$phase" "$dest_dir" -r "$req_file"
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
run_step "Извлечение зависимостей из pyproject.toml" python3 - "$PYPROJECT_FILE" "$req_file" "$INCLUDE_DEV" "${EXTRA_REQUIREMENTS[*]}" <<'PY'
import pathlib
import sys
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "Для чтения pyproject.toml нужен модуль tomllib (Python 3.11+) "
            "или установленный пакет tomli для Python 3.10."
        ) from exc

pyproject_path = pathlib.Path(sys.argv[1])
out_path = pathlib.Path(sys.argv[2])
include_dev = bool(int(sys.argv[3]))
extra_requirements = [item.strip() for item in sys.argv[4].split() if item.strip()]
with pyproject_path.open('rb') as fh:
    data = tomllib.load(fh)

requirements = []


def extend_if_strings(values):
    for value in values or []:
        if isinstance(value, str) and value.strip():
            requirements.append(value.strip())


def collect_project_dependencies():
    project = data.get("project", {})
    extend_if_strings(project.get("dependencies", []))
    if include_dev:
        optional = project.get("optional-dependencies", {})
        extend_if_strings(optional.get("dev", []))


def collect_dependency_groups():
    if not include_dev:
        return
    groups = data.get("dependency-groups", {})
    dev_group = groups.get("dev", [])
    for item in dev_group:
        if isinstance(item, str) and item.strip():
            requirements.append(item.strip())
        elif isinstance(item, dict):
            # Поддержка include-group (PEP 735), например { include-group = "lint" }.
            include_group = item.get("include-group")
            if not include_group:
                continue
            nested = groups.get(include_group, [])
            for nested_item in nested:
                if isinstance(nested_item, str) and nested_item.strip():
                    requirements.append(nested_item.strip())


def collect_poetry_dependencies():
    poetry = data.get("tool", {}).get("poetry", {})
    poetry_deps = poetry.get("dependencies", {})
    for name, spec in poetry_deps.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, str):
            requirements.append(f"{name}{spec if spec.startswith(('=', '<', '>', '!', '~')) else f'=={spec}'}")
        elif isinstance(spec, dict):
            version = spec.get("version")
            if isinstance(version, str) and version.strip():
                requirements.append(f"{name}{version if version.startswith(('=', '<', '>', '!', '~')) else f'=={version}'}")
            else:
                requirements.append(name)
    if include_dev:
        dev_group = poetry.get("group", {}).get("dev", {}).get("dependencies", {})
        for name, spec in dev_group.items():
            if isinstance(spec, str):
                requirements.append(f"{name}{spec if spec.startswith(('=', '<', '>', '!', '~')) else f'=={spec}'}")
            elif isinstance(spec, dict):
                version = spec.get("version")
                if isinstance(version, str) and version.strip():
                    requirements.append(f"{name}{version if version.startswith(('=', '<', '>', '!', '~')) else f'=={version}'}")
                else:
                    requirements.append(name)


collect_project_dependencies()
collect_dependency_groups()
collect_poetry_dependencies()
extend_if_strings(data.get("build-system", {}).get("requires", []))

seen = set()
ordered_unique = []
for req in requirements:
    if req not in seen:
        ordered_unique.append(req)
        seen.add(req)

# Добавляем pinned-зависимости из Dockerfile (если они ещё не входят в pyproject)
for extra in extra_requirements:
    if extra not in seen:
        ordered_unique.append(extra)
        seen.add(extra)

out_path.write_text('\n'.join(ordered_unique) + '\n', encoding='utf-8')
PY

deps_count="$(wc -l < "$req_file" | tr -d ' ')"
dev_suffix=""
if [[ "$INCLUDE_DEV" -eq 1 ]]; then
  dev_suffix=" +dev"
fi
log "Найдено зависимостей (прямые + build-system${dev_suffix}): ${deps_count}"
if [[ "$deps_count" -eq 0 ]]; then
  fail "Не удалось извлечь зависимости из pyproject.toml (получено 0 записей). Проверьте формат секций [project.dependencies]/[dependency-groups]/[tool.poetry.dependencies]."
fi
log "Список зависимостей для проверки wheelhouse:"
nl -ba "$req_file" | sed 's/^/[REQ] /'

TARGET_DOWNLOAD_ARGS=(
  "--only-binary=:all:"
  "--platform" "$TARGET_PLATFORM"
  "--python-version" "$TARGET_PYTHON_VERSION"
  "--implementation" "$TARGET_IMPLEMENTATION"
  "--abi" "$TARGET_ABI"
)

log "Целевая конфигурация wheel:"
log "  TARGET_PLATFORM=${TARGET_PLATFORM}"
log "  TARGET_PYTHON_VERSION=${TARGET_PYTHON_VERSION}"
log "  TARGET_IMPLEMENTATION=${TARGET_IMPLEMENTATION}"
log "  TARGET_ABI=${TARGET_ABI}"

log "  PYTORCH_CUDA_INDEX_URL=${PYTORCH_CUDA_INDEX_URL}"
log "  TORCH_VERSION=${TORCH_VERSION}"
log "  TORCHVISION_VERSION=${TORCHVISION_VERSION}"
log "  TORCHAUDIO_VERSION=${TORCHAUDIO_VERSION}"

download_cuda_torch_stack() {
  local wheel_dir="$1"
  log "Докачиваю CUDA torch stack из ${PYTORCH_CUDA_INDEX_URL}..."
  python3 -m pip download \
    --disable-pip-version-check \
    --retries "$PIP_RETRIES" \
    --timeout "$PIP_TIMEOUT" \
    --dest "$wheel_dir" \
    "${TARGET_DOWNLOAD_ARGS[@]}" \
    --index-url "$PYTORCH_CUDA_INDEX_URL" \
    "torch==${TORCH_VERSION}" \
    "torchvision==${TORCHVISION_VERSION}" \
    "torchaudio==${TORCHAUDIO_VERSION}"
}

validate_wheelhouse() {
  local wheel_dir="$1"
  local tmp_validate_dir
  tmp_validate_dir="$(mktemp -d)"
  log "Проверка wheelhouse: pip download --no-index --find-links ${wheel_dir}"
  if ! python3 -m pip download \
    --disable-pip-version-check \
    --dest "$tmp_validate_dir" \
    --no-index \
    --find-links "$wheel_dir" \
    "${TARGET_DOWNLOAD_ARGS[@]}" \
    -r "$req_file"; then
    rm -rf "$tmp_validate_dir"
    return 1
  fi
  rm -rf "$tmp_validate_dir"
}

preflight_check_available_versions() {
  local report_dir
  local preflight_err_log
  report_dir="$(mktemp -d)"
  preflight_err_log="$(mktemp)"
  local primary_index
  local extra_index
  local fallback_index
  primary_index="${PIP_INDEX_URL:-<pip default index>}"
  extra_index="${PIP_EXTRA_INDEX_URL:-<not set>}"
  fallback_index="${PIP_FALLBACK_INDEX_URL:-<not set>}"
  log "Проверка доступности зависимостей через индексы:"
  log "  PIP_INDEX_URL=${primary_index}"
  log "  PIP_EXTRA_INDEX_URL=${extra_index}"
  log "  PIP_FALLBACK_INDEX_URL=${fallback_index}"

  if ! download_requirements_with_fallback "$report_dir" "Preflight" 2>"$preflight_err_log"; then
    local endpoints
    endpoints="$(extract_unreachable_endpoints "$preflight_err_log" || true)"
    rm -f "$preflight_err_log"
    rm -rf "$report_dir"
    if [[ -n "$endpoints" ]]; then
      fail "Предварительная проверка зависимостей не пройдена: не удалось подключиться к ${endpoints} (retries=${PIP_RETRIES}, timeout=${PIP_TIMEOUT}s)."
    fi
    return 1
  fi
  rm -f "$preflight_err_log"

  local planned
  planned="$(find "$report_dir" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ')"
  rm -rf "$report_dir"
  if [[ "$planned" -eq 0 ]]; then
    return 1
  fi
  log "Предварительная проверка: pip смог скачать ${planned} wheel-файлов в dry-run каталоге"
}

log "Проверяю доступность требуемых версий (включая транзитивные зависимости) до загрузки wheelhouse..."
run_step "Preflight: проверка доступности версий и ссылок индекса" preflight_check_available_versions
ok "Предварительная проверка зависимостей пройдена"

if [[ "$MODE" == "append" ]]; then
  log "Режим append: докачиваю недостающие wheels в $WHEELS_DIR..."
  run_step "Append: загрузка wheels в существующий каталог" download_requirements_with_fallback "$WHEELS_DIR" "Append"

  run_step "Append: докачка CUDA torch stack" download_cuda_torch_stack "$WHEELS_DIR"

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
run_step "Refresh: загрузка wheels во временный каталог" download_requirements_with_fallback "$tmp_wheels_dir" "Refresh"

run_step "Refresh: докачка CUDA torch stack" download_cuda_torch_stack "$tmp_wheels_dir"

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
  run_step "Refresh: создание резервной копии текущего wheelhouse" mv "$WHEELS_DIR" "$backup_dir"
  log "Текущий wheelhouse сохранён в резервную копию: $backup_dir"
fi

if ! mv "$tmp_wheels_dir" "$WHEELS_DIR"; then
  if [[ -d "$backup_dir" ]]; then
    mv "$backup_dir" "$WHEELS_DIR" || true
  fi
  fail "Не удалось атомарно заменить wheelhouse. Выполнен откат (если возможно)."
fi

if [[ -d "$backup_dir" ]]; then
  run_step "Refresh: удаление резервной копии wheelhouse" rm -rf "$backup_dir"
fi

# Сохраняем служебный файл для пустого каталога в git.
# Файл .gitkeep не влияет на установку wheel, но нужен для отслеживания директории.
touch "${WHEELS_DIR}/.gitkeep"

ok "Wheelhouse успешно пересобран и проверен: $WHEELS_DIR"
