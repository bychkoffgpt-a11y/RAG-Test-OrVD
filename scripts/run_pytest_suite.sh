#!/usr/bin/env bash
set -euo pipefail

print_help() {
  cat <<'HELP'
Usage: run_pytest_suite.sh [OPTIONS] [PYTEST_ARGS...]

Run project tests from app/ virtual environment with import pre-check.

Options:
  -a, --app-dir PATH   Path to app directory (default: ./app)
  -u, --unit           Run only unit tests
  -i, --integration    Run only integration tests
  -h, --help           Show this help and exit

Any additional arguments are passed directly to pytest.

Examples:
  ./scripts/run_pytest_suite.sh
  ./scripts/run_pytest_suite.sh --unit -q
  ./scripts/run_pytest_suite.sh --integration -k openai_compat
HELP
}

APP_DIR="./app"
TARGET="all"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--app-dir) APP_DIR="$2"; shift 2 ;;
    -u|--unit) TARGET="unit"; shift ;;
    -i|--integration) TARGET="integration"; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

if [[ ! -f "$APP_DIR/pyproject.toml" ]]; then
  echo "ERROR: pyproject.toml not found in $APP_DIR"
  exit 1
fi
if [[ ! -f "$APP_DIR/.venv/bin/activate" ]]; then
  echo "ERROR: virtualenv not found. Run scripts/setup_python_env.sh first."
  exit 1
fi

cd "$APP_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[info] python: $(which python)"
python -V
echo "[info] pytest: $(which pytest)"
pytest --version

python - <<'PY'
import importlib
mods = [
    'fastapi',
    'pydantic',
    'pydantic_settings',
    'httpx',
    'sentence_transformers',
    'pypdf',
    'qdrant_client',
]
for mod in mods:
    importlib.import_module(mod)
print('OK: required imports are available')
PY

case "$TARGET" in
  unit) pytest -q tests/unit "${EXTRA_ARGS[@]}" ;;
  integration) pytest -q tests/integration "${EXTRA_ARGS[@]}" ;;
  *) pytest -q "${EXTRA_ARGS[@]}" ;;
esac
