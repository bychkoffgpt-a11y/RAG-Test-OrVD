#!/usr/bin/env bash
set -euo pipefail

echo "[WARN] Deprecated: use scripts/build_ingest_base.sh"
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build_ingest_base.sh" "$@"
