#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${ROOT_DIR}/models"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $1" >&2
    exit 1
  fi
}

need_cmd hf
need_cmd curl
need_cmd tar
need_cmd find

mkdir -p \
  "${MODELS_DIR}/llm" \
  "${MODELS_DIR}/vision/qwen3-vl-2b-instruct" \
  "${MODELS_DIR}/embeddings/bge-m3" \
  "${MODELS_DIR}/reranker/bge-reranker-v2-m3" \
  "${MODELS_DIR}/ocr/det" \
  "${MODELS_DIR}/ocr/rec" \
  "${MODELS_DIR}/ocr/cls"

LLM_HF_REPO="${LLM_HF_REPO:-Qwen/Qwen2.5-7B-Instruct-GGUF}"
LLM_MODEL_FILE="${LLM_MODEL_FILE:-qwen2.5-7b-instruct-q4_k_m.gguf}"

is_nonempty_file() {
  local path="$1"
  [[ -f "$path" && -s "$path" ]]
}

run_and_log() {
  echo "[CMD] $*"
  "$@"
}

ensure_hf_repo_snapshot() {
  local repo="$1"
  local target_dir="$2"
  local marker_file="$3"

  if is_nonempty_file "${target_dir}/${marker_file}"; then
    echo "[INFO] Already present, skip download: ${target_dir}/${marker_file}"
    return 0
  fi

  echo "[INFO] Downloading ${repo} -> ${target_dir}"
  run_and_log hf download "${repo}" --local-dir "${target_dir}"

  if ! is_nonempty_file "${target_dir}/${marker_file}"; then
    echo "[ERROR] Download finished, but required file is missing: ${target_dir}/${marker_file}" >&2
    exit 1
  fi
}

ensure_llm_file() {
  local repo="$1"
  local target_dir="$2"
  local required_file="$3"
  local target_path="${target_dir}/${required_file}"

  if is_nonempty_file "${target_path}"; then
    echo "[INFO] LLM already present, skip download: ${target_path}"
    return 0
  fi

  # Если файл уже есть в каталоге, но только в другом регистре имени (например, Q4_K_M),
  # приводим его к ожидаемому имени из LLM_MODEL_FILE.
  local existing_case_variant=""
  existing_case_variant="$(find "${target_dir}" -maxdepth 1 -type f -iname "${required_file}" -print -quit)"
  if [[ -n "${existing_case_variant}" ]]; then
    cp "${existing_case_variant}" "${target_path}"
    echo "[INFO] Found case-variant LLM file and normalized name: ${target_path}"
    return 0
  fi

  echo "[INFO] Downloading LLM from ${repo} (required file: ${required_file})"
  run_and_log hf download "${repo}" \
    --include "${required_file}" \
    --local-dir "${target_dir}"

  if is_nonempty_file "${target_path}"; then
    echo "[INFO] LLM downloaded: ${target_path}"
    return 0
  fi

  # Диагностика: возможно, в upstream имя отличается только регистром.
  existing_case_variant="$(find "${target_dir}" -maxdepth 1 -type f -iname "${required_file}" -print -quit)"
  if [[ -n "${existing_case_variant}" ]]; then
    cp "${existing_case_variant}" "${target_path}"
    echo "[INFO] LLM downloaded with case-variant name; normalized to: ${target_path}"
    return 0
  fi

  echo "[ERROR] Failed to download required LLM file: ${required_file}" >&2
  echo "[ERROR] Repo: ${repo}" >&2
  echo "[ERROR] Hint: check the exact filename in the Hugging Face repo and LLM_MODEL_FILE in .env." >&2
  echo "[ERROR] Current contents of ${target_dir}:" >&2
  find "${target_dir}" -maxdepth 1 -type f -printf "  - %f\n" >&2 || true
  exit 1
}

ensure_ocr_models() {
  local ocr_root="$1"
  local det_model="${ocr_root}/det/inference.pdmodel"
  local det_params="${ocr_root}/det/inference.pdiparams"
  local rec_model="${ocr_root}/rec/inference.pdmodel"
  local rec_params="${ocr_root}/rec/inference.pdiparams"
  local cls_model="${ocr_root}/cls/inference.pdmodel"
  local cls_params="${ocr_root}/cls/inference.pdiparams"

  if is_nonempty_file "${det_model}" \
    && is_nonempty_file "${det_params}" \
    && is_nonempty_file "${rec_model}" \
    && is_nonempty_file "${rec_params}" \
    && is_nonempty_file "${cls_model}" \
    && is_nonempty_file "${cls_params}"; then
    echo "[INFO] OCR models already present, skip download"
    return 0
  fi

  echo "[INFO] Downloading PaddleOCR det/rec/cls..."
  run_and_log curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar" -o "${TMP_DIR}/det.tar"
  run_and_log curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar" -o "${TMP_DIR}/rec.tar"
  run_and_log curl -fL "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar" -o "${TMP_DIR}/cls.tar"

  run_and_log tar -xf "${TMP_DIR}/det.tar" -C "${TMP_DIR}"
  run_and_log tar -xf "${TMP_DIR}/rec.tar" -C "${TMP_DIR}"
  run_and_log tar -xf "${TMP_DIR}/cls.tar" -C "${TMP_DIR}"

  run_and_log cp "${TMP_DIR}/ch_PP-OCRv4_det_infer/inference.pdmodel" "${MODELS_DIR}/ocr/det/"
  run_and_log cp "${TMP_DIR}/ch_PP-OCRv4_det_infer/inference.pdiparams" "${MODELS_DIR}/ocr/det/"
  run_and_log cp "${TMP_DIR}/ch_PP-OCRv4_rec_infer/inference.pdmodel" "${MODELS_DIR}/ocr/rec/"
  run_and_log cp "${TMP_DIR}/ch_PP-OCRv4_rec_infer/inference.pdiparams" "${MODELS_DIR}/ocr/rec/"
  run_and_log cp "${TMP_DIR}/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel" "${MODELS_DIR}/ocr/cls/"
  run_and_log cp "${TMP_DIR}/ch_ppocr_mobile_v2.0_cls_infer/inference.pdiparams" "${MODELS_DIR}/ocr/cls/"
}

echo "[INFO] Downloading Hugging Face models..."
ensure_llm_file "${LLM_HF_REPO}" "${MODELS_DIR}/llm" "${LLM_MODEL_FILE}"
ensure_hf_repo_snapshot "Qwen/Qwen3-VL-2B-Instruct" "${MODELS_DIR}/vision/qwen3-vl-2b-instruct" "config.json"
ensure_hf_repo_snapshot "BAAI/bge-m3" "${MODELS_DIR}/embeddings/bge-m3" "config.json"
ensure_hf_repo_snapshot "BAAI/bge-reranker-v2-m3" "${MODELS_DIR}/reranker/bge-reranker-v2-m3" "config.json"

ensure_ocr_models "${MODELS_DIR}/ocr"

echo "[INFO] Model download complete."
echo "[INFO] LLM path: ${MODELS_DIR}/llm/${LLM_MODEL_FILE}"
echo "[INFO] Next step: ./scripts/preflight_check.sh --mode offline --check-ocr-stack"
