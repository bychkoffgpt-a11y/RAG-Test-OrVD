#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/build_ingest_base.sh [options]

Build ingest base image from app/Dockerfile.ingest-base.

Options:
  -h, --help   Show this help and exit

Environment variables:
  IMAGE_REPO                Target image repository (default: ghcr.io/csv-ans/rag-ingest-base)
  PUSH_IMAGE                Push image after build (0|1, default: 0)
  PIP_INDEX_URL             Primary Python index for docker build args
  PIP_FALLBACK_INDEX_URL    Fallback/mirror Python index for docker build args
  PIP_EXTRA_INDEX_URL       Extra Python index for docker build args
  PIP_TRUSTED_HOST          Trusted host for pip (use only in controlled environments)
  PIP_MODE                  auto|offline|online (default: auto)
  PIP_ONLINE_FALLBACK       0|1 (default: 1)
  DEBIAN_MIRROR             Debian mirror URL for apt
  DEBIAN_SECURITY_MIRROR    Debian security mirror URL for apt
USAGE
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown argument: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/csv-ans/rag-ingest-base}"
PUSH_IMAGE="${PUSH_IMAGE:-0}"

PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
PIP_MODE="${PIP_MODE:-auto}"
PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK:-1}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-https://mirror.yandex.ru/debian}"
DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR:-https://mirror.yandex.ru/debian-security}"

if [[ ! -f "${APP_DIR}/pyproject.toml" ]]; then
  echo "[FAIL] pyproject.toml not found in ${APP_DIR}" >&2
  exit 1
fi

if [[ -d "${APP_DIR}/wheels" ]]; then
  WHEELS_HASH="$(find "${APP_DIR}/wheels" -maxdepth 1 -type f -name '*.whl' -print0 | sort -z | xargs -0 -r sha256sum 2>/dev/null | sha256sum | awk '{print $1}')"
else
  WHEELS_HASH="no-wheels"
fi

LOCK_INPUT_HASH="$({
  sha256sum "${APP_DIR}/pyproject.toml"
  sha256sum "${APP_DIR}/Dockerfile.ingest-base"
  printf '%s\n' "${WHEELS_HASH}"
} | sha256sum | awk '{print $1}')"

DEPS_TAG="deps-${LOCK_INPUT_HASH:0:16}"
IMAGE_REF="${IMAGE_REPO}:${DEPS_TAG}"

echo "[INFO] Dependency tag: ${DEPS_TAG}"
echo "[INFO] Building ${IMAGE_REF}"
echo "[INFO] pip indexes: primary=${PIP_INDEX_URL}, fallback=${PIP_FALLBACK_INDEX_URL:-<not set>}, extra=${PIP_EXTRA_INDEX_URL:-<not set>}"

if [[ -z "${PIP_FALLBACK_INDEX_URL}" ]]; then
  echo "[WARN] PIP_FALLBACK_INDEX_URL is not set. If primary TLS/network fails, there is no mirror fallback."
fi

docker build \
  -f "${APP_DIR}/Dockerfile.ingest-base" \
  --build-arg PIP_INDEX_URL="${PIP_INDEX_URL}" \
  --build-arg PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL}" \
  --build-arg PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
  --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
  --build-arg PIP_MODE="${PIP_MODE}" \
  --build-arg PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK}" \
  --build-arg DEBIAN_MIRROR="${DEBIAN_MIRROR}" \
  --build-arg DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR}" \
  -t "${IMAGE_REF}" \
  "${APP_DIR}"

if [[ "${PUSH_IMAGE}" == "1" ]]; then
  echo "[INFO] Pushing ${IMAGE_REF}"
  docker push "${IMAGE_REF}"
else
  echo "[INFO] Push skipped (set PUSH_IMAGE=1 to publish)."
fi

echo "[INFO] Export the tag for compose builds:"
echo "INGEST_DEPS_TAG=${DEPS_TAG}"
