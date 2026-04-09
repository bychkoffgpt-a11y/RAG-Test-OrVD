#!/usr/bin/env sh
set -eu

LLM_N_GPU_LAYERS_VALUE="${LLM_N_GPU_LAYERS:-99}"

case "${LLM_N_GPU_LAYERS_VALUE}" in
  ''|*[!0-9-]*)
    echo "ERROR: LLM_N_GPU_LAYERS must be a non-negative integer, got '${LLM_N_GPU_LAYERS_VALUE}'." >&2
    exit 64
    ;;
esac

if [ "${LLM_N_GPU_LAYERS_VALUE}" -gt 0 ]; then
  if [ ! -e /dev/nvidiactl ] && [ ! -e /dev/nvidia0 ]; then
    echo "ERROR: LLM_N_GPU_LAYERS=${LLM_N_GPU_LAYERS_VALUE}, but NVIDIA GPU devices are not available inside llm-server container." >&2
    echo "Ensure Docker Compose service 'llm-server' has 'gpus: all' and the host has a working NVIDIA Container Toolkit/WSL2 GPU setup." >&2
    exit 65
  fi

  if command -v nvidia-smi >/dev/null 2>&1; then
    if ! nvidia-smi -L >/dev/null 2>&1; then
      echo "ERROR: LLM_N_GPU_LAYERS=${LLM_N_GPU_LAYERS_VALUE}, but nvidia-smi cannot access GPU from inside llm-server container." >&2
      exit 66
    fi
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

exec "${LLAMA_SERVER_BIN}" "$@"
