#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./scripts/build_os_base_images.sh

Собирает OS base-образы (APT-слой), используемые в offline-first pipeline:
  - support-api OS base
  - ingest OS base

Параметры передаются через переменные окружения:
  SUPPORT_API_OS_BASE_IMAGE_REPO   Репозиторий support-api OS base
                                   (default: local/rag-support-api-os-base)
  INGEST_OS_BASE_IMAGE_REPO        Репозиторий ingest OS base
                                   (default: local/rag-ingest-os-base)
  OS_TAG                           Тег образов (default: latest)
  PUSH_IMAGE                       1 = выполнить docker push (default: 0)
  DEBIAN_MIRROR                    Debian mirror для support-api OS build
  DEBIAN_SECURITY_MIRROR           Debian security mirror для support-api OS build

Примеры:
  ./scripts/build_os_base_images.sh
  OS_TAG=2026-04-29 PUSH_IMAGE=1 ./scripts/build_os_base_images.sh
EOF
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/app"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a && . "${ROOT_DIR}/.env" && set +a
fi

SUPPORT_API_OS_BASE_IMAGE_REPO="${SUPPORT_API_OS_BASE_IMAGE_REPO:-local/rag-support-api-os-base}"
INGEST_OS_BASE_IMAGE_REPO="${INGEST_OS_BASE_IMAGE_REPO:-local/rag-ingest-os-base}"
OS_TAG="${OS_TAG:-latest}"
PUSH_IMAGE="${PUSH_IMAGE:-0}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-https://mirror.yandex.ru/debian}"
DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR:-https://mirror.yandex.ru/debian-security}"

SUPPORT_OS_REF="${SUPPORT_API_OS_BASE_IMAGE_REPO}:${OS_TAG}"
INGEST_OS_REF="${INGEST_OS_BASE_IMAGE_REPO}:${OS_TAG}"

echo "[INFO] Building support-api OS base: ${SUPPORT_OS_REF}"
docker build \
  -f "${APP_DIR}/Dockerfile.support-api-os-base" \
  --build-arg DEBIAN_MIRROR="${DEBIAN_MIRROR}" \
  --build-arg DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR}" \
  -t "${SUPPORT_OS_REF}" \
  "${APP_DIR}"

echo "[INFO] Building ingest OS base: ${INGEST_OS_REF}"
docker build \
  -f "${APP_DIR}/Dockerfile.ingest-os-base" \
  --build-arg SUPPORT_API_OS_BASE_IMAGE="${SUPPORT_OS_REF}" \
  -t "${INGEST_OS_REF}" \
  "${APP_DIR}"

if [[ "${PUSH_IMAGE}" == "1" ]]; then
  echo "[INFO] Pushing ${SUPPORT_OS_REF}"
  docker push "${SUPPORT_OS_REF}"
  echo "[INFO] Pushing ${INGEST_OS_REF}"
  docker push "${INGEST_OS_REF}"
fi

echo "[INFO] Export for offline/deps builds:"
echo "SUPPORT_API_OS_BASE_IMAGE=${SUPPORT_OS_REF}"
echo "INGEST_OS_BASE_IMAGE=${INGEST_OS_REF}"
