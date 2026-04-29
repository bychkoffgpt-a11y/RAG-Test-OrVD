#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * p))))
    return float(ordered[idx])


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail if /chat latency p95 exceeds threshold.")
    ap.add_argument("--input", required=True, help="JSONL file from run_vlm_chat_completions.py")
    ap.add_argument("--threshold-ms", type=float, required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    lat = [float(r.get("latency_ms", 0.0) or 0.0) for r in rows if not r.get("error")]
    p95 = percentile(lat, 0.95)
    print(f"chat_latency_ms_p95={p95:.2f} threshold_ms={args.threshold_ms:.2f} samples={len(lat)}")
    if p95 > args.threshold_ms:
        print("FAIL: p95 threshold exceeded.")
        return 1
    print("OK: p95 threshold check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
