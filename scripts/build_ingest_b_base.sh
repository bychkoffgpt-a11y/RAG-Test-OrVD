#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./scripts/build_ingest_b_base.sh [options]

Deprecated compatibility wrapper.
Этот скрипт оставлен для обратной совместимости и просто перенаправляет
вызов в основной скрипт:
  ./scripts/build_ingest_base.sh

Рекомендуется использовать напрямую:
  ./scripts/build_ingest_base.sh --help

Любые переданные аргументы/флаги будут без изменений переданы в
build_ingest_base.sh.
EOF
  exit 0
fi

echo "[WARN] Deprecated: use scripts/build_ingest_base.sh"
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build_ingest_base.sh" "$@"
