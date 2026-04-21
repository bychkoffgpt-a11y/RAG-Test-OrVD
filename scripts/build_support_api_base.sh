#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT_DIR}/.env" && set +a
fi

IMAGE_REPO="${IMAGE_REPO:-${SUPPORT_API_BASE_IMAGE_REPO:-ghcr.io/csv-ans/rag-support-api-base}}"
PUSH_IMAGE="${PUSH_IMAGE:-0}"
PIP_MODE="${PIP_MODE:-auto}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK:-1}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-https://mirror.yandex.ru/debian}"
DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR:-https://mirror.yandex.ru/debian-security}"
SUPPORT_API_OS_BASE_IMAGE="${SUPPORT_API_OS_BASE_IMAGE:-${SUPPORT_API_OS_BASE_IMAGE_REPO:-local/rag-support-api-os-base}:${SUPPORT_API_OS_TAG:-latest}}"

if [[ ! -f "${APP_DIR}/pyproject.toml" ]]; then
  echo "[FAIL] pyproject.toml not found in ${APP_DIR}" >&2
  exit 1
fi

if [[ -d "${APP_DIR}/wheels" ]]; then
  WHEELS_HASH="$(find "${APP_DIR}/wheels" -maxdepth 1 -type f -name '*.whl' -print0 | sort -z | xargs -0 -r sha256sum 2>/dev/null | sha256sum | awk '{print $1}')"
else
  WHEELS_HASH="no-wheels"
fi

if [[ "${PIP_MODE}" == "offline" ]]; then
  if ! find "${APP_DIR}/wheels" -mindepth 1 -maxdepth 1 -type f -name '*.whl' -print -quit | grep -q .; then
    echo "[FAIL] PIP_MODE=offline requires non-empty ${APP_DIR}/wheels" >&2
    exit 1
  fi
  if ! docker image inspect "${SUPPORT_API_OS_BASE_IMAGE}" >/dev/null 2>&1; then
    echo "[FAIL] PIP_MODE=offline requires prebuilt OS base image locally: ${SUPPORT_API_OS_BASE_IMAGE}" >&2
    exit 1
  fi
fi

LOCK_INPUT_HASH="$({
  sha256sum "${APP_DIR}/pyproject.toml"
  sha256sum "${APP_DIR}/Dockerfile.support-api-base"
  printf '%s\n' "${WHEELS_HASH}"
} | sha256sum | awk '{print $1}')"

DEPS_TAG="deps-${LOCK_INPUT_HASH:0:16}"
IMAGE_REF="${IMAGE_REPO}:${DEPS_TAG}"

echo "[INFO] Dependency tag: ${DEPS_TAG}"
echo "[INFO] Building ${IMAGE_REF}"
echo "[INFO] OS base image: ${SUPPORT_API_OS_BASE_IMAGE}"

docker build \
  -f "${APP_DIR}/Dockerfile.support-api-base" \
  --build-arg PIP_INDEX_URL="${PIP_INDEX_URL}" \
  --build-arg PIP_FALLBACK_INDEX_URL="${PIP_FALLBACK_INDEX_URL}" \
  --build-arg PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL}" \
  --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
  --build-arg PIP_MODE="${PIP_MODE}" \
  --build-arg PIP_ONLINE_FALLBACK="${PIP_ONLINE_FALLBACK}" \
  --build-arg DEBIAN_MIRROR="${DEBIAN_MIRROR}" \
  --build-arg DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR}" \
  --build-arg SUPPORT_API_OS_BASE_IMAGE="${SUPPORT_API_OS_BASE_IMAGE}" \
  -t "${IMAGE_REF}" \
  "${APP_DIR}"

if [[ "${PUSH_IMAGE}" == "1" ]]; then
  echo "[INFO] Pushing ${IMAGE_REF}"
  docker push "${IMAGE_REF}"
else
  echo "[INFO] Push skipped (set PUSH_IMAGE=1 to publish)."
fi

echo "[INFO] Export the tag for compose builds:"
echo "SUPPORT_API_DEPS_TAG=${DEPS_TAG}"
