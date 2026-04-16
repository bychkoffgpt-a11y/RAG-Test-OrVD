#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/csv-ans/rag-ingest-base}"
PUSH_IMAGE="${PUSH_IMAGE:-0}"

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

docker build \
  -f "${APP_DIR}/Dockerfile.ingest-base" \
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
