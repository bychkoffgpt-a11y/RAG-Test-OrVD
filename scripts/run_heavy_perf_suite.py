#!/usr/bin/env python3
"""Запуск тяжёлого performance-suite для /ask с длинными вопросами и тяжёлыми изображениями.

Сценарии задаются JSON-файлом. Для каждого кейса скрипт:
1) делает warmup-запросы (опционально);
2) выполняет N рабочих итераций /ask;
3) сохраняет per-run latency/статусы;
4) снимает дельты Prometheus-метрик rag_stage_duration_seconds (sum/count) по этапам.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class StageAgg:
    count: float = 0.0
    total: float = 0.0


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Cases file must be a non-empty JSON array")
    return payload


def _build_question(case: dict[str, Any]) -> str:
    question = (case.get("question") or "").strip()
    if not question:
        question_file = (case.get("question_file") or "").strip()
        if not question_file:
            raise ValueError("Case must provide either 'question' or 'question_file'")
        question = Path(question_file).read_text(encoding="utf-8").strip()
    repeat = int(case.get("question_repeat", 1) or 1)
    if repeat > 1:
        question = "\n\n".join([question] * repeat)
    return question


def _post_json(url: str, payload: dict[str, Any], timeout_sec: float) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            duration = time.perf_counter() - started
            return status, data, duration
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        parsed = json.loads(raw) if raw else {"detail": raw or str(exc)}
        duration = time.perf_counter() - started
        return int(exc.code), parsed, duration


def _fetch_text(url: str, timeout_sec: float) -> str:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")


def _parse_stage_metrics(metrics_text: str) -> dict[tuple[str, str, str], StageAgg]:
    # key = (stage, has_attachments, metric_type[sum|count])
    out: dict[tuple[str, str, str], StageAgg] = {}
    for line in metrics_text.splitlines():
        if not line.startswith("rag_stage_duration_seconds_"):
            continue
        if "{" not in line or "}" not in line:
            continue
        left, value_str = line.split(" ", 1)
        metric_name = left.split("{", 1)[0]
        labels_raw = left.split("{", 1)[1].rsplit("}", 1)[0]
        labels: dict[str, str] = {}
        for part in labels_raw.split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            labels[k] = v.strip('"')
        endpoint = labels.get("endpoint")
        stage = labels.get("stage")
        has_att = labels.get("has_attachments")
        if endpoint != "/ask" or not stage or has_att not in {"0", "1"}:
            continue

        metric_type = None
        if metric_name.endswith("_sum"):
            metric_type = "sum"
        elif metric_name.endswith("_count"):
            metric_type = "count"
        else:
            continue

        key = (stage, has_att, metric_type)
        agg = out.setdefault(key, StageAgg())
        if metric_type == "sum":
            agg.total = float(value_str.strip())
        else:
            agg.count = float(value_str.strip())
    return out


def _snapshot_metrics(api_url: str, timeout_sec: float) -> dict[tuple[str, str, str], StageAgg]:
    text = _fetch_text(f"{api_url.rstrip('/')}/metrics", timeout_sec)
    return _parse_stage_metrics(text)


def _delta_stage_means(
    before: dict[tuple[str, str, str], StageAgg],
    after: dict[tuple[str, str, str], StageAgg],
    has_attachments: str,
) -> dict[str, dict[str, float]]:
    stages: dict[str, dict[str, float]] = {}
    stage_names = {
        key[0]
        for key in before.keys() | after.keys()
        if key[1] == has_attachments and key[2] in {"sum", "count"}
    }
    for stage in sorted(stage_names):
        sum_before = before.get((stage, has_attachments, "sum"), StageAgg()).total
        sum_after = after.get((stage, has_attachments, "sum"), StageAgg()).total
        count_before = before.get((stage, has_attachments, "count"), StageAgg()).count
        count_after = after.get((stage, has_attachments, "count"), StageAgg()).count
        delta_count = max(0.0, count_after - count_before)
        delta_sum = max(0.0, sum_after - sum_before)
        mean = delta_sum / delta_count if delta_count > 0 else 0.0
        stages[stage] = {
            "delta_count": delta_count,
            "delta_sum_sec": delta_sum,
            "mean_sec": mean,
        }
    return stages


def _q95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def _run_case(case: dict[str, Any], api_url: str, timeout_sec: float, out_dir: Path) -> dict[str, Any]:
    name = str(case.get("name") or "").strip()
    if not name:
        raise ValueError("Case field 'name' is required")

    question = _build_question(case)
    top_k = int(case.get("top_k", 8))
    scope = str(case.get("scope", "all"))
    image_path = str(case.get("image_path") or "").strip()
    iterations = int(case.get("iterations", 5))
    warmup_runs = int(case.get("warmup_runs", 1))
    sleep_sec = float(case.get("sleep_sec", 0.5))

    payload: dict[str, Any] = {
        "question": question,
        "top_k": top_k,
        "scope": scope,
        "attachments": [{"image_path": image_path}] if image_path else [],
    }

    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)

    for i in range(warmup_runs):
        status, _, lat = _post_json(f"{api_url.rstrip('/')}/ask", payload, timeout_sec)
        print(f"[warmup] {name} #{i+1}/{warmup_runs}: status={status} latency={lat:.3f}s")
        time.sleep(sleep_sec)

    before = _snapshot_metrics(api_url, timeout_sec)

    runs: list[dict[str, Any]] = []
    for i in range(iterations):
        status, response, latency = _post_json(f"{api_url.rstrip('/')}/ask", payload, timeout_sec)
        run = {
            "iteration": i + 1,
            "status": status,
            "latency_sec": latency,
            "sources_count": len(response.get("sources") or []),
            "images_count": len(response.get("images") or []),
            "visual_evidence_count": len(response.get("visual_evidence") or []),
            "answer_chars": len((response.get("answer") or "")),
        }
        runs.append(run)
        print(f"[run] {name} #{i+1}/{iterations}: status={status} latency={latency:.3f}s")
        time.sleep(sleep_sec)

    after = _snapshot_metrics(api_url, timeout_sec)
    has_att_label = "1" if image_path else "0"
    stage_deltas = _delta_stage_means(before, after, has_att_label)

    lat_values = [r["latency_sec"] for r in runs]
    summary = {
        "runs": len(runs),
        "status_ok_ratio": sum(1 for r in runs if 200 <= r["status"] < 300) / max(1, len(runs)),
        "ask_latency_sec": {
            "p50": statistics.median(lat_values) if lat_values else 0.0,
            "p95": _q95(lat_values),
            "max": max(lat_values) if lat_values else 0.0,
            "mean": statistics.mean(lat_values) if lat_values else 0.0,
        },
    }

    report = {
        "case": {
            "name": name,
            "question_chars": len(question),
            "question_repeat": int(case.get("question_repeat", 1) or 1),
            "top_k": top_k,
            "scope": scope,
            "image_path": image_path,
            "iterations": iterations,
            "warmup_runs": warmup_runs,
            "sleep_sec": sleep_sec,
        },
        "summary": summary,
        "runs": runs,
        "stage_deltas": stage_deltas,
    }

    (case_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run heavy performance suite for /ask")
    parser.add_argument("--api-url", default="http://localhost:8000", help="support-api URL")
    parser.add_argument("--cases-file", required=True, help="Path to cases JSON")
    parser.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout in seconds")
    parser.add_argument("--out-root", default="data/rag_traces/heavy_suite", help="Output root directory")
    args = parser.parse_args()

    cases_file = Path(args.cases_file).resolve()
    cases = _load_cases(cases_file)

    suite_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_root).resolve() / suite_name
    out_dir.mkdir(parents=True, exist_ok=True)

    all_reports = []
    for case in cases:
        report = _run_case(case, api_url=args.api_url, timeout_sec=args.timeout, out_dir=out_dir)
        all_reports.append(report)

    suite_summary = {
        "meta": {
            "api_url": args.api_url,
            "cases_file": str(cases_file),
            "suite_name": suite_name,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "cases": all_reports,
    }
    (out_dir / "suite_summary.json").write_text(json.dumps(suite_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Heavy suite results saved to: {out_dir}")
    print(f"[OK] Suite summary: {out_dir / 'suite_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
