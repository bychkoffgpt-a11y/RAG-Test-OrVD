#!/usr/bin/env bash
set -euo pipefail

print_help() {
  cat <<'HELP'
Usage: setup_python_env.sh [OPTIONS]

Create and bootstrap Python virtual environment for app tests.

Options:
  -a, --app-dir PATH     Path to app directory (default: ./app)
  -p, --python BIN       Python executable to use for venv (default: python3)
  --recreate             Remove existing .venv before creating
  --no-upgrade-tools     Skip pip/setuptools/wheel upgrade
  -h, --help             Show this help and exit

Environment variables (loaded from <app-dir>/.env if present):
  PIP_INDEX_URL            Primary index URL
  PIP_FALLBACK_INDEX_URL   Fallback index URL used when primary fails
  PIP_EXTRA_INDEX_URL      Extra index URL (e.g. torch wheels)
  PIP_TRUSTED_HOST         Optional trusted host for pip

Examples:
  ./scripts/setup_python_env.sh
  ./scripts/setup_python_env.sh --python python3.12 --recreate
  ./scripts/setup_python_env.sh --app-dir /opt/RAG-Test-OrVD/app
HELP
}

APP_DIR="./app"
PYTHON_BIN="python3"
RECREATE=0
UPGRADE_TOOLS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--app-dir) APP_DIR="$2"; shift 2 ;;
    -p|--python) PYTHON_BIN="$2"; shift 2 ;;
    --recreate) RECREATE=1; shift ;;
    --no-upgrade-tools) UPGRADE_TOOLS=0; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Unknown argument: $1"; print_help; exit 2 ;;
  esac
done

if [[ ! -f "$APP_DIR/pyproject.toml" ]]; then
  echo "ERROR: pyproject.toml not found in $APP_DIR"
  exit 1
fi

cd "$APP_DIR"

if [[ "$RECREATE" -eq 1 && -d ".venv" ]]; then
  rm -rf .venv
fi

"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-60}"
export PIP_RETRIES="${PIP_RETRIES:-8}"
export PIP_DISABLE_PIP_VERSION_CHECK=1

pip_install() {
  local index_url="${1:-}"

  local cmd=(python -m pip install)
  if [[ -n "$index_url" ]]; then
    cmd+=(--index-url "$index_url")
  fi
  if [[ -n "${PIP_EXTRA_INDEX_URL:-}" ]]; then
    cmd+=(--extra-index-url "$PIP_EXTRA_INDEX_URL")
  fi
  if [[ -n "${PIP_TRUSTED_HOST:-}" ]]; then
    cmd+=(--trusted-host "$PIP_TRUSTED_HOST")
  fi

  if [[ "$UPGRADE_TOOLS" -eq 1 ]]; then
    "${cmd[@]}" -U pip setuptools wheel
  fi
  "${cmd[@]}" -e '.[dev]'
}

if pip_install "${PIP_INDEX_URL:-}"; then
  echo "[ok] dependencies installed using primary index"
else
  if [[ -n "${PIP_FALLBACK_INDEX_URL:-}" ]]; then
    echo "[warn] primary index failed, retrying with fallback index"
    pip_install "$PIP_FALLBACK_INDEX_URL"
    echo "[ok] dependencies installed using fallback index"
  else
    echo "[error] installation failed and PIP_FALLBACK_INDEX_URL is not set"
    exit 1
  fi
fi

echo "[info] python: $(which python)"
python -V
echo "[info] pytest: $(which pytest)"
pytest --version
