#!/usr/bin/env sh
set -eu

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
  exec /opt/llm_log_sanitizer.py "${LLAMA_SERVER_BIN}" "$@"
fi

exec "${LLAMA_SERVER_BIN}" "$@"
