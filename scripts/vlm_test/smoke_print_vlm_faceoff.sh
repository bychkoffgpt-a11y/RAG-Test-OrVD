#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

GOOD_JSONL="${TMP_DIR}/vlm_ask_results.jsonl"
BAD_SUMMARY="${TMP_DIR}/vlm_ask_score_v2_summary.json"

cat > "${GOOD_JSONL}" <<'EOF'
{"id":"img01","answer_text":"На изображении есть stop sign","golden_facts":["stop sign"],"negative_facts":["speed limit 80"]}
EOF

cat > "${BAD_SUMMARY}" <<'EOF'
{"summary":{"cases_total":1}}
EOF

echo "[smoke] valid JSONL should pass"
python3 "${ROOT_DIR}/print_vlm_faceoff.py" --input "${GOOD_JSONL}" >/dev/null

echo "[smoke] summary JSON should fail with format error"
if python3 "${ROOT_DIR}/print_vlm_faceoff.py" --input "${BAD_SUMMARY}" >/tmp/faceoff_bad.out 2>&1; then
  echo "ERROR: summary JSON unexpectedly accepted"
  exit 1
fi

if ! rg -q "Expected input format: JSONL" /tmp/faceoff_bad.out; then
  echo "ERROR: expected format hint not found in error output"
  cat /tmp/faceoff_bad.out
  exit 1
fi

echo "[smoke] OK"
