#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
QUESTION="${QUESTION:-Почему не обработались записи по UHOP?}"
IMAGE_PATH="${IMAGE_PATH:-}"
TOP_K="${TOP_K:-8}"
SCOPE="${SCOPE:-all}"
ITERATIONS="${ITERATIONS:-3}"
TIMEOUT="${TIMEOUT:-120}"
OUT_ROOT="${OUT_ROOT:-data/rag_traces/profiles}"
PROFILE_NAME="${PROFILE_NAME:-}"
COMPARE_WITH="${COMPARE_WITH:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url) API_URL="$2"; shift 2 ;;
    --question) QUESTION="$2"; shift 2 ;;
    --image-path) IMAGE_PATH="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --iterations) ITERATIONS="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --profile-name) PROFILE_NAME="$2"; shift 2 ;;
    --compare-with) COMPARE_WITH="$2"; shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/profile_latency.sh [options]

Build repeatable latency profile for /ask via scripts/trace_rag_pipeline.py.

Options:
  --api-url URL           support-api URL (default: http://localhost:8000)
  --question TEXT         question for /ask
  --image-path PATH       optional attachment path (inside support-api container)
  --top-k N               top_k (default: 8)
  --scope S               all|csv_ans_docs|internal_regulations (default: all)
  --iterations N          number of /ask runs (default: 3)
  --timeout SEC           per-run timeout (default: 120)
  --out-root DIR          root output dir (default: data/rag_traces/profiles)
  --profile-name NAME     explicit profile folder name
  --compare-with DIR      compare current profile with existing profile dir

Examples:
  scripts/profile_latency.sh --iterations 5 --profile-name baseline_ocr
  scripts/profile_latency.sh --iterations 5 --profile-name candidate_vlm --compare-with data/rag_traces/profiles/baseline_ocr
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PROFILE_NAME" ]]; then
  PROFILE_NAME="$(date -u +%Y%m%dT%H%M%SZ)"
fi

PROFILE_DIR="${OUT_ROOT%/}/${PROFILE_NAME}"
mkdir -p "$PROFILE_DIR"
RUNS_DIR="$PROFILE_DIR/runs"
mkdir -p "$RUNS_DIR"

for ((i=1; i<=ITERATIONS; i++)); do
  RUN_OUT_DIR="$RUNS_DIR/run_${i}"
  mkdir -p "$RUN_OUT_DIR"
  echo "[INFO] run ${i}/${ITERATIONS} -> ${RUN_OUT_DIR}"
  python3 scripts/trace_rag_pipeline.py \
    --api-url "$API_URL" \
    --question "$QUESTION" \
    --image-path "$IMAGE_PATH" \
    --top-k "$TOP_K" \
    --scope "$SCOPE" \
    --timeout "$TIMEOUT" \
    --out-dir "$RUN_OUT_DIR" \
    --write-markdown

  sleep 1
done

python3 - <<'PY' "$PROFILE_DIR" "$API_URL" "$QUESTION" "$IMAGE_PATH" "$TOP_K" "$SCOPE" "$ITERATIONS" "$COMPARE_WITH"
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

profile_dir = Path(sys.argv[1])
api_url = sys.argv[2]
question = sys.argv[3]
image_path = sys.argv[4]
top_k = int(sys.argv[5])
scope = sys.argv[6]
iterations = int(sys.argv[7])
compare_with = sys.argv[8].strip()

json_files = sorted(profile_dir.glob('runs/run_*/trace_*.json'))
if not json_files:
    raise SystemExit('[FAIL] trace JSON files not found')

rows = []
for path in json_files:
    payload = json.loads(path.read_text(encoding='utf-8'))
    ask_call = payload.get('ask_call', {})
    pipeline = payload.get('pipeline_trace', {})
    profile = payload.get('runtime_profile', {})
    rows.append(
        {
            'file': str(path),
            'status': int(ask_call.get('status', 0) or 0),
            'ask_latency_sec': float(profile.get('ask_latency_sec', 0.0) or 0.0),
            'orchestrator_total_sec': float(profile.get('orchestrator_total_sec', 0.0) or 0.0),
            'vision_sec': float(profile.get('orchestrator_vision_sec', 0.0) or 0.0),
            'llm_sec': float(profile.get('orchestrator_llm_generation_sec', 0.0) or 0.0),
            'visual_evidence_count': len(pipeline.get('visual_evidence') or []),
            'contexts_count': len((pipeline.get('retrieval') or {}).get('contexts_used_for_prompt') or []),
            'vision_runtime_mode': (pipeline.get('settings_snapshot') or {}).get('vision_runtime_mode'),
        }
    )


def q95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def summarize(rows_in: list[dict]) -> dict:
    ask_lat = [r['ask_latency_sec'] for r in rows_in]
    orch_lat = [r['orchestrator_total_sec'] for r in rows_in if r['orchestrator_total_sec'] > 0]
    vis_lat = [r['vision_sec'] for r in rows_in]
    llm_lat = [r['llm_sec'] for r in rows_in]
    return {
        'runs': len(rows_in),
        'status_ok_ratio': sum(1 for r in rows_in if 200 <= r['status'] < 300) / max(1, len(rows_in)),
        'ask_latency_sec': {'p50': statistics.median(ask_lat), 'p95': q95(ask_lat), 'max': max(ask_lat)},
        'orchestrator_total_sec': {
            'p50': statistics.median(orch_lat) if orch_lat else 0.0,
            'p95': q95(orch_lat) if orch_lat else 0.0,
            'max': max(orch_lat) if orch_lat else 0.0,
        },
        'vision_sec': {'p50': statistics.median(vis_lat), 'p95': q95(vis_lat), 'max': max(vis_lat)},
        'llm_sec': {'p50': statistics.median(llm_lat), 'p95': q95(llm_lat), 'max': max(llm_lat)},
        'avg_visual_evidence_count': statistics.mean(r['visual_evidence_count'] for r in rows_in),
        'avg_contexts_count': statistics.mean(r['contexts_count'] for r in rows_in),
        'vision_runtime_mode': rows_in[0].get('vision_runtime_mode') if rows_in else None,
    }

summary = {
    'meta': {
        'api_url': api_url,
        'question': question,
        'image_path': image_path,
        'top_k': top_k,
        'scope': scope,
        'iterations_requested': iterations,
    },
    'runs': rows,
    'summary': summarize(rows),
}

summary_path = profile_dir / 'summary.json'
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

md_lines = [
    '# Latency profile report',
    '',
    '## Meta',
    f'- api_url: `{api_url}`',
    f'- scope: `{scope}`',
    f'- top_k: `{top_k}`',
    f'- iterations: `{len(rows)}`',
    f'- image_path: `{image_path or "(empty)"}`',
    f'- vision_runtime_mode: `{summary["summary"].get("vision_runtime_mode")}`',
    '',
    '## Aggregates',
    f"- ask latency p50/p95/max: `{summary['summary']['ask_latency_sec']['p50']:.3f}` / `{summary['summary']['ask_latency_sec']['p95']:.3f}` / `{summary['summary']['ask_latency_sec']['max']:.3f}` sec",
    f"- orchestrator total p50/p95/max: `{summary['summary']['orchestrator_total_sec']['p50']:.3f}` / `{summary['summary']['orchestrator_total_sec']['p95']:.3f}` / `{summary['summary']['orchestrator_total_sec']['max']:.3f}` sec",
    f"- vision stage p50/p95/max: `{summary['summary']['vision_sec']['p50']:.3f}` / `{summary['summary']['vision_sec']['p95']:.3f}` / `{summary['summary']['vision_sec']['max']:.3f}` sec",
    f"- llm stage p50/p95/max: `{summary['summary']['llm_sec']['p50']:.3f}` / `{summary['summary']['llm_sec']['p95']:.3f}` / `{summary['summary']['llm_sec']['max']:.3f}` sec",
    f"- status_ok_ratio: `{summary['summary']['status_ok_ratio']:.2%}`",
    '',
]

if compare_with:
    base_dir = Path(compare_with)
    base_summary_path = base_dir / 'summary.json'
    if base_summary_path.exists():
        base_summary = json.loads(base_summary_path.read_text(encoding='utf-8'))
        cur = summary['summary']
        base = base_summary['summary']

        def delta(metric: str, stat: str) -> float:
            return float(cur.get(metric, {}).get(stat, 0.0)) - float(base.get(metric, {}).get(stat, 0.0))

        md_lines.extend(
            [
                '## Comparison vs baseline',
                f'- baseline: `{base_dir}`',
                f"- Δ ask p95: `{delta('ask_latency_sec', 'p95'):+.3f}` sec",
                f"- Δ orchestrator total p95: `{delta('orchestrator_total_sec', 'p95'):+.3f}` sec",
                f"- Δ vision p95: `{delta('vision_sec', 'p95'):+.3f}` sec",
                f"- Δ llm p95: `{delta('llm_sec', 'p95'):+.3f}` sec",
                '',
                '> Positive delta means current profile is slower than baseline.',
                '',
            ]
        )
    else:
        md_lines.extend([
            '## Comparison vs baseline',
            f'- baseline summary not found: `{base_summary_path}`',
            '',
        ])

md_path = profile_dir / 'summary.md'
md_path.write_text('\n'.join(md_lines), encoding='utf-8')

print(f'[OK] profile summary: {summary_path}')
print(f'[OK] profile markdown: {md_path}')
PY

echo "[DONE] profile ready: $PROFILE_DIR"
