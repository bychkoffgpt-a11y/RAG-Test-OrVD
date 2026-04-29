#!/usr/bin/env python3
import argparse
import re
from collections import defaultdict

RE_TRACE = re.compile(r'trace_id[="\:\s]+([a-zA-Z0-9\-_]+)')
STAGES = [
    "ask.request_received",
    "ask.request_parsed",
    "ask.route_selected",
    "ask.vision_preprocess_done",
    "ask.vlm_called",
    "ask.response_ready",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-file", required=True)
    args = ap.parse_args()

    traces = defaultdict(set)
    with open(args.log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = RE_TRACE.search(line)
            if not m:
                continue
            tid = m.group(1)
            for s in STAGES:
                if s in line:
                    traces[tid].add(s)

    print(f"Traces found: {len(traces)}")
    for tid, stages in list(traces.items())[:200]:
        missing = [s for s in STAGES if s not in stages]
        if missing:
            print(f"[BROKEN] trace_id={tid} missing={missing}")
        else:
            print(f"[OK] trace_id={tid} all stages present")


if __name__ == "__main__":
    main()
