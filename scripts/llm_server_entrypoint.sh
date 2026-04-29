#!/usr/bin/env sh
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
Usage: /usr/local/bin/llm_server_entrypoint.sh [llama-server args...]

Container entrypoint for llama-server with validation and optional log sanitization.

What this script does:
  1) Unsets LLAMA_ARG_HOST to avoid duplicate host warnings.
  2) Validates LLM_N_GPU_LAYERS (must be non-negative integer).
  3) Warns if GPU layers are requested but nvidia-smi is unavailable.
  4) Locates llama-server binary (PATH or /app/llama-server).
  5) If LLM_LOG_SANITIZER=1 and sanitizer is available, starts llama-server
     through /opt/llm_log_sanitizer.py.

Environment variables:
  LLM_N_GPU_LAYERS   Number of GPU layers for llama.cpp (default: 99).
  LLM_LOG_SANITIZER  1 to enable sanitizer wrapper, 0 to disable (default: 1).

Examples:
  /usr/local/bin/llm_server_entrypoint.sh --host 0.0.0.0 --port 8080 -m /models/llm.gguf
  LLM_LOG_SANITIZER=0 /usr/local/bin/llm_server_entrypoint.sh -m /models/llm.gguf
EOF
  exit 0
fi

# Avoid duplicate host configuration warnings from llama-server.
unset LLAMA_ARG_HOST || true

LLM_N_GPU_LAYERS_VALUE="${LLM_N_GPU_LAYERS:-99}"

case "${LLM_N_GPU_LAYERS_VALUE}" in
  ''|*[!0-9-]*)
    echo "ERROR: LLM_N_GPU_LAYERS must be a non-negative integer, got '${LLM_N_GPU_LAYERS_VALUE}'." >&2
    exit 64
    ;;
esac

if [ "${LLM_N_GPU_LAYERS_VALUE}" -gt 0 ] && command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi -L >/dev/null 2>&1; then
    echo "WARN: LLM_N_GPU_LAYERS=${LLM_N_GPU_LAYERS_VALUE}, but nvidia-smi cannot access GPU from inside llm-server container." >&2
    echo "Proceeding with configured '-ngl ${LLM_N_GPU_LAYERS_VALUE}' (no forced CPU fallback)." >&2
  fi
fi

if command -v llama-server >/dev/null 2>&1; then
  LLAMA_SERVER_BIN="$(command -v llama-server)"
elif [ -x /app/llama-server ]; then
  LLAMA_SERVER_BIN="/app/llama-server"
else
  echo "ERROR: Unable to locate llama-server binary in container." >&2
  exit 67
fi


LOG_SANITIZER="${LLM_LOG_SANITIZER:-1}"
if [ "${LOG_SANITIZER}" = "1" ] && [ -x /opt/llm_log_sanitizer.py ]; then
  if command -v python3 >/dev/null 2>&1; then
    exec /opt/llm_log_sanitizer.py "${LLAMA_SERVER_BIN}" "$@"
  else
    echo "WARN: LLM_LOG_SANITIZER=1, but python3 is not available in container; starting llama-server without sanitizer." >&2
  fi
fi

exec "${LLAMA_SERVER_BIN}" "$@"
