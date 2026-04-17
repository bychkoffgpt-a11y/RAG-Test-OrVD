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

need_cmd huggingface-cli
need_cmd curl
need_cmd tar

mkdir -p \
  "${MODELS_DIR}/vision/qwen3-vl-2b-instruct" \
  "${MODELS_DIR}/embeddings/bge-m3" \
  "${MODELS_DIR}/reranker/bge-reranker-v2-m3" \
  "${MODELS_DIR}/ocr/det" \
  "${MODELS_DIR}/ocr/rec" \
  "${MODELS_DIR}/ocr/cls"

echo "[INFO] Downloading Hugging Face models..."
huggingface-cli download Qwen/Qwen3-VL-2B-Instruct \
  --local-dir "${MODELS_DIR}/vision/qwen3-vl-2b-instruct"

huggingface-cli download BAAI/bge-m3 \
  --local-dir "${MODELS_DIR}/embeddings/bge-m3"

huggingface-cli download BAAI/bge-reranker-v2-m3 \
  --local-dir "${MODELS_DIR}/reranker/bge-reranker-v2-m3"

echo "[INFO] Downloading PaddleOCR det/rec/cls..."
curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar" -o "${TMP_DIR}/det.tar"
curl -fL "https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar" -o "${TMP_DIR}/rec.tar"
curl -fL "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar" -o "${TMP_DIR}/cls.tar"

tar -xf "${TMP_DIR}/det.tar" -C "${TMP_DIR}"
tar -xf "${TMP_DIR}/rec.tar" -C "${TMP_DIR}"
tar -xf "${TMP_DIR}/cls.tar" -C "${TMP_DIR}"

cp "${TMP_DIR}/ch_PP-OCRv4_det_infer/inference.pdmodel" "${MODELS_DIR}/ocr/det/"
cp "${TMP_DIR}/ch_PP-OCRv4_det_infer/inference.pdiparams" "${MODELS_DIR}/ocr/det/"
cp "${TMP_DIR}/ch_PP-OCRv4_rec_infer/inference.pdmodel" "${MODELS_DIR}/ocr/rec/"
cp "${TMP_DIR}/ch_PP-OCRv4_rec_infer/inference.pdiparams" "${MODELS_DIR}/ocr/rec/"
cp "${TMP_DIR}/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel" "${MODELS_DIR}/ocr/cls/"
cp "${TMP_DIR}/ch_ppocr_mobile_v2.0_cls_infer/inference.pdiparams" "${MODELS_DIR}/ocr/cls/"

echo "[INFO] Model download complete."
echo "[INFO] Next step: ./scripts/preflight_check.sh --mode offline --check-ocr-stack"
