#!/usr/bin/env python3
import argparse
import json
import re
from collections import defaultdict

RE_TRACE = re.compile(r'(?:trace_id|request_id|correlation_id)[="\:\s]+([a-zA-Z0-9\-_]+)')
STAGES = [
    "image_preprocess_start",
    "image_preprocess_end",
    "vlm_infer_start",
    "vlm_infer_end",
    "parse_start",
    "parse_end",
    "finalize",
]
TRACE_LOGGER_HINTS = {"src.rag.orchestrator", "src.vision.service", "src.main"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-file", required=True)
    args = ap.parse_args()

    traces = defaultdict(set)
    trace_lines = 0
    json_lines = 0
    matched_logger_lines = 0
    with open(args.log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            payload = None
            stripped = line.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                    json_lines += 1
                except json.JSONDecodeError:
                    payload = None

            if payload:
                logger_name = str(payload.get("logger", ""))
                if logger_name in TRACE_LOGGER_HINTS:
                    matched_logger_lines += 1
                tid = (
                    payload.get("trace_id")
                    or payload.get("request_id")
                    or payload.get("correlation_id")
                )
                stage = str(payload.get("stage", "")).strip()
                message = str(payload.get("message", "")).strip()
                if stage:
                    stage_text = stage
                else:
                    event = str(payload.get("event", ""))
                    stage_text = f"{message} {event}".strip()
                if tid and stage:
                    trace_lines += 1
            else:
                m = RE_TRACE.search(line)
                if not m:
                    continue
                tid = m.group(1)
                stage_text = line

            if not tid:
                continue
            for s in STAGES:
                if s in stage_text:
                    traces[tid].add(s)

    print(f"Traces found: {len(traces)}")
    if len(traces) == 0:
        print("[ZERO_TRACES] reason=no_trace_id_or_stage_in_logs")
        print(f"[ZERO_TRACES] json_lines={json_lines} matched_logger_lines={matched_logger_lines} trace_stage_lines={trace_lines}")
        print("[ZERO_TRACES] expected_fields=trace_id,stage,vision_mode,latency_ms,tokens_in,tokens_out")
        return
    for tid, stages in list(traces.items())[:200]:
        missing = [s for s in STAGES if s not in stages]
        if missing:
            print(f"[BROKEN] trace_id={tid} missing={missing}")
        else:
            print(f"[OK] trace_id={tid} all stages present")


if __name__ == "__main__":
    main()
