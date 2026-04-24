#!/usr/bin/env python3
"""Агрегация и сравнение результатов heavy performance-suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_suite(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "cases" not in data:
        raise ValueError("suite_summary.json has invalid format")
    return data


def _top_stage(stage_deltas: dict[str, dict[str, float]]) -> tuple[str, float]:
    best_name = "n/a"
    best_sec = 0.0
    for stage, vals in stage_deltas.items():
        mean = float(vals.get("mean_sec", 0.0) or 0.0)
        if mean > best_sec:
            best_name = stage
            best_sec = mean
    return best_name, best_sec


def _fmt_sec(v: float) -> str:
    return f"{v:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze heavy performance suite results")
    parser.add_argument("--suite-dir", required=True, help="Directory with suite_summary.json")
    args = parser.parse_args()

    suite_dir = Path(args.suite_dir).resolve()
    summary_path = suite_dir / "suite_summary.json"
    suite = _load_suite(summary_path)

    rows: list[dict[str, Any]] = []
    for case in suite.get("cases", []):
        case_meta = case.get("case", {})
        sum_meta = case.get("summary", {}).get("ask_latency_sec", {})
        stage_deltas = case.get("stage_deltas", {})
        top_stage, top_stage_mean = _top_stage(stage_deltas)

        rows.append(
            {
                "name": case_meta.get("name", "unknown"),
                "question_chars": int(case_meta.get("question_chars", 0) or 0),
                "has_image": bool(case_meta.get("image_path")),
                "iterations": int(case_meta.get("iterations", 0) or 0),
                "status_ok_ratio": float(case.get("summary", {}).get("status_ok_ratio", 0.0) or 0.0),
                "ask_p50": float(sum_meta.get("p50", 0.0) or 0.0),
                "ask_p95": float(sum_meta.get("p95", 0.0) or 0.0),
                "ask_max": float(sum_meta.get("max", 0.0) or 0.0),
                "ask_mean": float(sum_meta.get("mean", 0.0) or 0.0),
                "top_stage": top_stage,
                "top_stage_mean_sec": top_stage_mean,
                "stage_deltas": stage_deltas,
            }
        )

    rows.sort(key=lambda x: x["ask_p95"], reverse=True)

    md_lines: list[str] = []
    md_lines.append("# Heavy perf suite analysis")
    md_lines.append("")
    md_lines.append(f"- Suite dir: `{suite_dir}`")
    md_lines.append(f"- Cases: `{len(rows)}`")
    md_lines.append("")

    md_lines.append("## Ranking by ask p95")
    md_lines.append("")
    md_lines.append("| # | case | chars | image | p50 | p95 | max | top stage | top stage mean | ok ratio |")
    md_lines.append("|---:|---|---:|:---:|---:|---:|---:|---|---:|---:|")
    for idx, row in enumerate(rows, start=1):
        md_lines.append(
            "| {idx} | {name} | {chars} | {img} | {p50} | {p95} | {max_} | {top_stage} | {top_mean} | {ok:.2%} |".format(
                idx=idx,
                name=row["name"],
                chars=row["question_chars"],
                img="yes" if row["has_image"] else "no",
                p50=_fmt_sec(row["ask_p50"]),
                p95=_fmt_sec(row["ask_p95"]),
                max_=_fmt_sec(row["ask_max"]),
                top_stage=row["top_stage"],
                top_mean=_fmt_sec(row["top_stage_mean_sec"]),
                ok=row["status_ok_ratio"],
            )
        )

    md_lines.append("")
    md_lines.append("## Stage breakdown per case (mean sec from Prometheus deltas)")
    md_lines.append("")
    for row in rows:
        md_lines.append(f"### {row['name']}")
        stage_items = sorted(
            row["stage_deltas"].items(), key=lambda item: float(item[1].get("mean_sec", 0.0) or 0.0), reverse=True
        )
        if not stage_items:
            md_lines.append("- (no stage data)")
            md_lines.append("")
            continue
        for stage, vals in stage_items:
            md_lines.append(
                f"- `{stage}`: mean=`{_fmt_sec(float(vals.get('mean_sec', 0.0) or 0.0))}` sec, "
                f"delta_count=`{int(float(vals.get('delta_count', 0.0) or 0.0))}`"
            )
        md_lines.append("")

    md = "\n".join(md_lines) + "\n"
    md_path = suite_dir / "analysis.md"
    md_path.write_text(md, encoding="utf-8")

    json_path = suite_dir / "analysis.json"
    json_path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Analysis markdown: {md_path}")
    print(f"[OK] Analysis json: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
