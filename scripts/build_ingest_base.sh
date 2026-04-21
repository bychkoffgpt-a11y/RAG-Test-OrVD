#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/build_ingest_base.sh [options]

Build ingest base image from app/Dockerfile.ingest-base.

Options:
  -h, --help   Show this help and exit

Environment variables:
  IMAGE_REPO                Target image repository (default: INGEST_BASE_IMAGE_REPO from .env)
  PUSH_IMAGE                Push image after build (0|1, default: 0)
  PIP_INDEX_URL             Primary Python index for docker build args
  PIP_FALLBACK_INDEX_URL    Fallback/mirror Python index for docker build args
  PIP_EXTRA_INDEX_URL       Extra Python index for docker build args
  PIP_TRUSTED_HOST          Trusted host for pip (use only in controlled environments)
  PIP_MODE                  auto|offline|online (default: auto)
  PIP_ONLINE_FALLBACK       0|1 (default: 1)
  DEBIAN_MIRROR             Debian mirror URL for apt
  DEBIAN_SECURITY_MIRROR    Debian security mirror URL for apt
  INGEST_OS_BASE_IMAGE      Prebuilt ingest OS base image reference
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

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT_DIR}/.env" && set +a
fi

IMAGE_REPO="${IMAGE_REPO:-${INGEST_BASE_IMAGE_REPO:-}}"
PUSH_IMAGE="${PUSH_IMAGE:-0}"

if [[ -z "${IMAGE_REPO}" ]]; then
  echo "[FAIL] IMAGE_REPO is not set. Configure INGEST_BASE_IMAGE_REPO in .env or pass IMAGE_REPO=..." >&2
  exit 1
fi

PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
PIP_MODE="${PIP_MODE:-auto}"
PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK:-1}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-https://mirror.yandex.ru/debian}"
DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR:-https://mirror.yandex.ru/debian-security}"
INGEST_OS_BASE_IMAGE="${INGEST_OS_BASE_IMAGE:-${INGEST_OS_BASE_IMAGE_REPO:-local/rag-ingest-os-base}:${INGEST_OS_TAG:-latest}}"

if [[ "${IMAGE_REPO}" == cr.yandex/* ]]; then
  if command -v yc >/dev/null 2>&1; then
    if [[ "${YC_DOCKER_AUTH:-1}" == "1" ]]; then
      echo "[INFO] Configuring Docker auth for Yandex Container Registry via yc..."
      yc container registry configure-docker >/dev/null
    fi
  else
    echo "[WARN] yc CLI is not available. Ensure 'docker login' was done for cr.yandex."
  fi
fi

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
echo "[INFO] OS base image: ${INGEST_OS_BASE_IMAGE}"

if [[ -z "${PIP_FALLBACK_INDEX_URL}" ]]; then
  echo "[WARN] PIP_FALLBACK_INDEX_URL is not set. If primary TLS/network fails, there is no mirror fallback."
fi

if [[ "${PIP_MODE}" == "offline" ]]; then
  if ! find "${APP_DIR}/wheels" -mindepth 1 -maxdepth 1 -type f -name '*.whl' -print -quit | grep -q .; then
    echo "[FAIL] PIP_MODE=offline requires non-empty ${APP_DIR}/wheels" >&2
    exit 1
  fi
  if ! docker image inspect "${INGEST_OS_BASE_IMAGE}" >/dev/null 2>&1; then
    echo "[FAIL] PIP_MODE=offline requires prebuilt OS base image locally: ${INGEST_OS_BASE_IMAGE}" >&2
    exit 1
  fi
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
  --build-arg INGEST_OS_BASE_IMAGE="${INGEST_OS_BASE_IMAGE}" \
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
