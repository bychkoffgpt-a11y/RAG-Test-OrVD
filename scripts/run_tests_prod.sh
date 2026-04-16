#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
APP_DIR="${ROOT_DIR}/app"
GROUPS_RAW="all"
EXTRA_PYTEST_ARGS=()
LIST_GROUPS=0
USE_COVERAGE=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/run_tests_prod.sh [--groups all|unit|integration|group1,group2] [--coverage] [--list-groups] [-- <extra pytest args>]

Runs pytest in an isolated disposable Docker container based on the deployed support-api image.
Can run all tests or selected test groups without restarting production services.

Options:
  --groups VALUE    Test groups to run (default: all).
                    Supported values: all, unit, integration.
                    You can pass several groups separated by comma, e.g. unit,integration.
  --coverage        Add coverage report: --cov=src --cov-report=term-missing
  --list-groups     Print supported groups and exit
  -h, --help        Show this help
  --                Pass all following options directly to pytest

Examples:
  ./scripts/run_tests_prod.sh
  ./scripts/run_tests_prod.sh --groups unit
  ./scripts/run_tests_prod.sh --groups integration -- -k sources_download
  ./scripts/run_tests_prod.sh --groups unit,integration --coverage
USAGE
}

log() {
  echo "[INFO] $*"
}

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

ensure_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Command not found: $1"
}

parse_groups() {
  local raw="$1"
  local -a split_groups=()
  local group

  IFS=',' read -r -a split_groups <<< "$raw"
  if [[ ${#split_groups[@]} -eq 0 ]]; then
    fail "No groups specified in --groups"
  fi

  GROUP_PATHS=()
  for group in "${split_groups[@]}"; do
    case "$group" in
      all)
        GROUP_PATHS+=("tests")
        ;;
      unit)
        GROUP_PATHS+=("tests/unit")
        ;;
      integration)
        GROUP_PATHS+=("tests/integration")
        ;;
      "")
        fail "Empty group name in --groups '$raw'"
        ;;
      *)
        fail "Unknown group '$group'. Run with --list-groups"
        ;;
    esac
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --groups)
      [[ $# -ge 2 ]] || { usage; fail "Missing value for --groups"; }
      GROUPS_RAW="$2"
      shift 2
      ;;
    --list-groups)
      LIST_GROUPS=1
      shift
      ;;
    --coverage)
      USE_COVERAGE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_PYTEST_ARGS=("$@")
      break
      ;;
    *)
      usage
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ "$LIST_GROUPS" -eq 1 ]]; then
  cat <<'GROUPS'
Supported groups:
  all          -> app/tests
  unit         -> app/tests/unit
  integration  -> app/tests/integration
GROUPS
  exit 0
fi

ensure_cmd docker
ensure_cmd git

[[ -f "$COMPOSE_FILE" ]] || fail "docker-compose.yml not found at $COMPOSE_FILE"
[[ -d "$APP_DIR/tests" ]] || fail "Tests directory not found: $APP_DIR/tests"

parse_groups "$GROUPS_RAW"

log "Using groups: $GROUPS_RAW"

pytest_cmd=(pytest -q)
if [[ "$USE_COVERAGE" -eq 1 ]]; then
  pytest_cmd+=(--cov=src --cov-report=term-missing)
fi
pytest_cmd+=("${GROUP_PATHS[@]}")
if [[ ${#EXTRA_PYTEST_ARGS[@]} -gt 0 ]]; then
  pytest_cmd+=("${EXTRA_PYTEST_ARGS[@]}")
fi

quoted_pytest_cmd=$(printf ' %q' "${pytest_cmd[@]}")

log "Launching disposable container from service 'support-api'"
log "Pytest command:${quoted_pytest_cmd}"

cd "$ROOT_DIR"
docker compose run --rm --no-deps \
  -v "$APP_DIR:/workspace/app:ro" \
  support-api \
  bash -lc "set -euo pipefail; \
    cd /workspace/app; \
    export PYTHONDONTWRITEBYTECODE=1; \
    python -c 'import pytest' >/dev/null 2>&1 || python -m pip install --disable-pip-version-check pytest==8.3.3 pytest-cov==5.0.0 >/dev/null; \
    ${quoted_pytest_cmd} -o cache_dir=/tmp/pytest-cache"

log "Tests finished successfully"
