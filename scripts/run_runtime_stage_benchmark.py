#!/usr/bin/env python3
"""Бенчмарк runtime-этапов /ask по trace-карточкам.

Цели:
- получить разложение по этапам: vision, embedding, vector_search, rerank, llm_generation;
- стабилизировать тест за счёт adaptive-подбора payload при 5xx.

Скрипт отправляет запросы в /ask с уникальным X-Request-ID,
затем считывает trace JSON (data/rag_traces/ui_requests/...) с тем же request_id.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunResult:
    request_id: str
    status: int
    latency_sec: float
    trace_path: str | None
    timings: dict[str, float]
    answer_chars: int
    sources_count: int
    visual_evidence_count: int


def _q95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def _post_json(url: str, payload: dict[str, Any], timeout_sec: float, request_id: str) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            duration = time.perf_counter() - started
            return resp.status, (json.loads(raw) if raw else {}), duration
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        duration = time.perf_counter() - started
        parsed = json.loads(raw) if raw else {"detail": raw or str(exc)}
        return int(exc.code), parsed, duration


def _load_question(args: argparse.Namespace) -> str:
    if args.question:
        question = args.question.strip()
    else:
        question = Path(args.question_file).read_text(encoding="utf-8").strip()
    if args.question_repeat > 1:
        question = "\n\n".join([question] * args.question_repeat)
    return question


def _find_trace(trace_root: Path, request_id: str, wait_sec: float) -> Path | None:
    deadline = time.time() + max(0.0, wait_sec)
    pattern = f"*_{request_id}.json"
    while True:
        matches = sorted(trace_root.rglob(pattern))
        if matches:
            return matches[-1]
        if time.time() >= deadline:
            return None
        time.sleep(0.25)


def _extract_timings(trace_payload: dict[str, Any]) -> dict[str, float]:
    agg = trace_payload.get("aggregate_timings_sec") or {}
    out: dict[str, float] = {}
    for key in (
        "pre_processing",
        "vision",
        "embedding",
        "vector_search",
        "rerank",
        "retrieval_total",
        "prompt_build",
        "llm_generation",
        "post_formatting",
        "total",
    ):
        out[key] = float(agg.get(key, 0.0) or 0.0)
    return out


def _make_payload(question: str, top_k: int, scope: str, image_path: str) -> dict[str, Any]:
    return {
        "question": question,
        "top_k": top_k,
        "scope": scope,
        "attachments": [{"image_path": image_path}] if image_path else [],
    }


def _adaptive_preset(
    *,
    api_url: str,
    timeout_sec: float,
    scope: str,
    image_path: str,
    base_question: str,
    top_k: int,
    max_attempts: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    question = base_question
    current_top_k = top_k

    for i in range(1, max_attempts + 1):
        request_id = f"warmup-{uuid.uuid4().hex[:16]}"
        payload = _make_payload(question, current_top_k, scope, image_path)
        status, resp, latency = _post_json(f"{api_url.rstrip('/')}/ask", payload, timeout_sec, request_id=request_id)
        attempts.append(
            {
                "attempt": i,
                "status": status,
                "latency_sec": latency,
                "top_k": current_top_k,
                "question_chars": len(question),
                "detail": resp.get("detail") if isinstance(resp, dict) else None,
            }
        )
        print(
            f"[adaptive] attempt={i}/{max_attempts} status={status} "
            f"lat={latency:.3f}s top_k={current_top_k} q_chars={len(question)}"
        )
        if 200 <= status < 300:
            return payload, attempts

        # 1) сначала уменьшаем top_k
        if current_top_k > 4:
            current_top_k = max(4, current_top_k // 2)
            continue

        # 2) затем ужимаем длину вопроса
        if len(question) > 2200:
            question = question[: max(1800, int(len(question) * 0.75))]
            continue

        # 3) финальный fallback
        question = "Сформулируй краткий ответ по найденным источникам."

    return _make_payload(question, current_top_k, scope, image_path), attempts


def _summarize(runs: list[RunResult]) -> dict[str, Any]:
    lat = [r.latency_sec for r in runs]
    ok_runs = [r for r in runs if 200 <= r.status < 300]

    stage_keys = (
        "vision",
        "embedding",
        "vector_search",
        "rerank",
        "retrieval_total",
        "prompt_build",
        "llm_generation",
        "total",
    )
    stage_summary: dict[str, dict[str, float]] = {}
    for key in stage_keys:
        vals = [r.timings.get(key, 0.0) for r in ok_runs if r.timings]
        stage_summary[key] = {
            "mean": statistics.mean(vals) if vals else 0.0,
            "p50": statistics.median(vals) if vals else 0.0,
            "p95": _q95(vals),
            "max": max(vals) if vals else 0.0,
        }

    return {
        "runs": len(runs),
        "ok_runs": len(ok_runs),
        "status_ok_ratio": len(ok_runs) / max(1, len(runs)),
        "ask_latency_sec": {
            "mean": statistics.mean(lat) if lat else 0.0,
            "p50": statistics.median(lat) if lat else 0.0,
            "p95": _q95(lat),
            "max": max(lat) if lat else 0.0,
        },
        "stages_sec": stage_summary,
    }


def _write_outputs(out_dir: Path, report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    lines = [
        "# Runtime stage benchmark",
        "",
        f"- generated_at_utc: `{report['meta']['generated_at_utc']}`",
        f"- mode_hint: `{report['meta'].get('mode_hint', '')}`",
        f"- reranker_hint: `{report['meta'].get('reranker_hint', '')}`",
        f"- ok_ratio: `{s['status_ok_ratio']:.2%}` ({s['ok_runs']}/{s['runs']})",
        "",
        "## Ask latency",
        "",
        f"- mean/p50/p95/max: `{s['ask_latency_sec']['mean']:.3f}` / `{s['ask_latency_sec']['p50']:.3f}` / "
        f"`{s['ask_latency_sec']['p95']:.3f}` / `{s['ask_latency_sec']['max']:.3f}` sec",
        "",
        "## Stage breakdown (successful runs only)",
        "",
        "| stage | mean | p50 | p95 | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage, vals in s["stages_sec"].items():
        lines.append(
            f"| {stage} | {vals['mean']:.3f} | {vals['p50']:.3f} | {vals['p95']:.3f} | {vals['max']:.3f} |"
        )

    lines.extend(["", "## Key focus", ""])
    lines.append(
        "- retrieval decomposition: `embedding + vector_search + rerank` (см. строки выше)."
    )
    lines.append("- vision timing отражает OCR/VLM в зависимости от текущего `VISION_RUNTIME_MODE`.")
    lines.append("- если ok_ratio низкий, сначала стабилизируйте payload через adaptive-подбор.")
    lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark runtime stages by /ask trace cards")
    q_group = parser.add_mutually_exclusive_group(required=True)
    q_group.add_argument("--question", help="Question text")
    q_group.add_argument("--question-file", help="Path to question text file")

    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--scope", default="all", choices=["all", "csv_ans_docs", "internal_regulations"])
    parser.add_argument("--image-path", default="", help="Optional image attachment path inside support-api container")
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--sleep-sec", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--question-repeat", type=int, default=1)
    parser.add_argument("--adaptive", action="store_true", help="Enable adaptive pre-run to avoid 5xx")
    parser.add_argument("--adaptive-max-attempts", type=int, default=6)
    parser.add_argument("--trace-root", default="data/rag_traces/ui_requests")
    parser.add_argument("--trace-wait-sec", type=float, default=6.0)
    parser.add_argument("--mode-hint", default="", help="Optional marker for report (e.g. ocr/vlm)")
    parser.add_argument("--reranker-hint", default="", help="Optional marker for report (e.g. on/off)")
    parser.add_argument("--out-root", default="data/rag_traces/runtime_stage_benchmark")

    args = parser.parse_args()

    question = _load_question(args)
    payload = _make_payload(question, args.top_k, args.scope, args.image_path)

    adaptive_log: list[dict[str, Any]] = []
    if args.adaptive:
        payload, adaptive_log = _adaptive_preset(
            api_url=args.api_url,
            timeout_sec=args.timeout,
            scope=args.scope,
            image_path=args.image_path,
            base_question=question,
            top_k=args.top_k,
            max_attempts=args.adaptive_max_attempts,
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.mode_hint or "default"
    out_dir = Path(args.out_root).resolve() / f"{ts}_{label}"
    trace_root = Path(args.trace_root).resolve()

    for i in range(args.warmup_runs):
        request_id = f"warm-{uuid.uuid4().hex}"
        status, _, lat = _post_json(f"{args.api_url.rstrip('/')}/ask", payload, args.timeout, request_id=request_id)
        print(f"[warmup] {i+1}/{args.warmup_runs} status={status} latency={lat:.3f}s")
        time.sleep(args.sleep_sec)

    runs: list[RunResult] = []
    for i in range(args.iterations):
        request_id = f"bench-{uuid.uuid4().hex}"
        status, resp, lat = _post_json(f"{args.api_url.rstrip('/')}/ask", payload, args.timeout, request_id=request_id)

        trace_path = None
        timings: dict[str, float] = {}
        if 200 <= status < 300:
            trace = _find_trace(trace_root, request_id, wait_sec=args.trace_wait_sec)
            if trace is not None:
                trace_payload = json.loads(trace.read_text(encoding="utf-8"))
                timings = _extract_timings(trace_payload)
                trace_path = str(trace)

        run = RunResult(
            request_id=request_id,
            status=status,
            latency_sec=lat,
            trace_path=trace_path,
            timings=timings,
            answer_chars=len((resp.get("answer") or "")) if isinstance(resp, dict) else 0,
            sources_count=len((resp.get("sources") or [])) if isinstance(resp, dict) else 0,
            visual_evidence_count=len((resp.get("visual_evidence") or [])) if isinstance(resp, dict) else 0,
        )
        runs.append(run)
        print(
            f"[run] {i+1}/{args.iterations} status={status} latency={lat:.3f}s "
            f"trace={'yes' if trace_path else 'no'}"
        )
        time.sleep(args.sleep_sec)

    report = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "api_url": args.api_url,
            "mode_hint": args.mode_hint,
            "reranker_hint": args.reranker_hint,
            "payload": payload,
            "trace_root": str(trace_root),
        },
        "adaptive": adaptive_log,
        "runs": [
            {
                "request_id": r.request_id,
                "status": r.status,
                "latency_sec": r.latency_sec,
                "trace_path": r.trace_path,
                "timings": r.timings,
                "answer_chars": r.answer_chars,
                "sources_count": r.sources_count,
                "visual_evidence_count": r.visual_evidence_count,
            }
            for r in runs
        ],
        "summary": _summarize(runs),
    }

    _write_outputs(out_dir, report)
    print(f"[OK] Report dir: {out_dir}")
    print(f"[OK] JSON: {out_dir / 'report.json'}")
    print(f"[OK] MD: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
