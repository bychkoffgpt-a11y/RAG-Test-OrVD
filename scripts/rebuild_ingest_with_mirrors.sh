#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/csv-ans/rag-ingest-base}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.ustc.edu.cn/pypi/simple}"
PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL:-https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
PIP_MODE="${PIP_MODE:-auto}"
PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK:-1}"

usage() {
  cat <<'USAGE'
Usage: ./scripts/rebuild_ingest_with_mirrors.sh [--skip-tls-check] [--skip-wheelhouse]

Rebuild flow for ingest-a/ingest-b in one sequence:
  1) (optional) TLS check for primary/fallback PyPI mirrors
  2) refresh wheelhouse in strict mode
  3) build ingest base image with selected indexes
  4) build docker compose services ingest-a and ingest-b

Options:
  --skip-tls-check   Skip TLS availability checks for mirror hosts
  --skip-wheelhouse  Skip wheelhouse refresh step
  -h, --help         Show help

Environment variables:
  IMAGE_REPO                Base image repository (default: ghcr.io/csv-ans/rag-ingest-base)
  PIP_INDEX_URL             Primary PyPI index URL (default: USTC mirror)
  PIP_FALLBACK_INDEX_URL    Fallback PyPI index URL (default: TUNA mirror)
  PIP_EXTRA_INDEX_URL       Optional extra index URL
  PIP_TRUSTED_HOST          Optional trusted host for pip
  PIP_MODE                  auto|offline|online (default: auto)
  PIP_ONLINE_FALLBACK       0|1 (default: 1)
USAGE
}

SKIP_TLS_CHECK=0
SKIP_WHEELHOUSE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tls-check)
      SKIP_TLS_CHECK=1
      shift
      ;;
    --skip-wheelhouse)
      SKIP_WHEELHOUSE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown parameter: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "${APP_DIR}/pyproject.toml" ]]; then
  echo "[FAIL] pyproject.toml not found in ${APP_DIR}" >&2
  exit 1
fi

echo "[INFO] repo: ${ROOT_DIR}"
echo "[INFO] mirror primary: ${PIP_INDEX_URL}"
echo "[INFO] mirror fallback: ${PIP_FALLBACK_INDEX_URL}"

if [[ "${SKIP_TLS_CHECK}" != "1" ]]; then
  echo "[INFO] Running TLS checks for mirrors..."
  python3 - "${PIP_INDEX_URL}" "${PIP_FALLBACK_INDEX_URL}" <<'PY'
import socket
import ssl
import sys
import urllib.parse

urls = [u for u in sys.argv[1:] if u]
checked = set()
for url in urls:
    host = urllib.parse.urlparse(url).hostname
    if not host or host in checked:
        continue
    checked.add(host)
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                print(f"[OK] TLS {host}:443")
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"[FAIL] TLS check failed for {host}:443 -> {exc}")
PY
fi

if [[ "${SKIP_WHEELHOUSE}" != "1" ]]; then
  echo "[INFO] Refreshing wheelhouse in strict mode..."
  "${ROOT_DIR}/scripts/update_wheels.sh" --mode refresh --strict
else
  echo "[WARN] Wheelhouse refresh skipped (--skip-wheelhouse)."
fi

echo "[INFO] Building ingest base image..."
BUILD_LOG="$(mktemp)"
IMAGE_REPO="${IMAGE_REPO}" \
PIP_INDEX_URL="${PIP_INDEX_URL}" \
PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL}" \
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
PIP_MODE="${PIP_MODE}" \
PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK}" \
"${ROOT_DIR}/scripts/build_ingest_base.sh" | tee "${BUILD_LOG}"

INGEST_DEPS_TAG="$(awk -F= '/^INGEST_DEPS_TAG=/{print $2}' "${BUILD_LOG}" | tail -n1)"
rm -f "${BUILD_LOG}"

if [[ -z "${INGEST_DEPS_TAG}" ]]; then
  echo "[FAIL] Could not determine INGEST_DEPS_TAG from build output." >&2
  exit 1
fi

export INGEST_BASE_IMAGE_REPO="${IMAGE_REPO}"
export INGEST_DEPS_TAG

echo "[INFO] Rebuilding ingest services with ${INGEST_BASE_IMAGE_REPO}:${INGEST_DEPS_TAG}"
docker compose build --no-cache ingest-a ingest-b

echo "[OK] Done."
echo "[OK] INGEST_BASE_IMAGE_REPO=${INGEST_BASE_IMAGE_REPO}"
echo "[OK] INGEST_DEPS_TAG=${INGEST_DEPS_TAG}"
