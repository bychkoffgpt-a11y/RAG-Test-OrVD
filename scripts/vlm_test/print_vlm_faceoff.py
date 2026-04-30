#!/usr/bin/env python3
"""Console face-off view: expected vs actual facts for VLM runs."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _is_summary_filename(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith("_summary.json") or name.endswith("_v2_summary.json")


def _summary_to_results_candidate(path: Path) -> Path | None:
    name = path.name
    candidates = []
    if name.endswith("_score_v2_summary.json"):
        candidates.append(name.replace("_score_v2_summary.json", "_results.jsonl"))
    if name.endswith("_score_summary.json"):
        candidates.append(name.replace("_score_summary.json", "_results.jsonl"))
    if name.endswith("_summary.json"):
        candidates.append(name.replace("_summary.json", "_results.jsonl"))

    for c in candidates:
        candidate = path.with_name(c)
        if candidate.exists():
            return candidate
    return None


def _format_hint(path: Path) -> str:
    hint = (
        "Expected input format: JSONL where each line is a case object "
        "with fields like 'id', 'answer_text', 'golden_facts', 'negative_facts'.\n"
        f"Got: {path}\n"
        "Example of a correct file: scripts/vlm_test/out/<timestamp>/vlm_ask_results.jsonl"
    )

    suggested = _summary_to_results_candidate(path)
    if suggested is not None:
        hint += f"\nDetected summary file. Try this results file instead: {suggested}"
    return hint


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if _is_summary_filename(path):
        raise ValueError(
            "Summary JSON is not supported by print_vlm_faceoff.py.\n" + _format_hint(path)
        )

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL: line {line_no} is not valid JSON ({exc}).\n"
                    + _format_hint(path)
                ) from exc

            if not isinstance(obj, dict):
                raise ValueError(
                    f"Invalid JSONL: line {line_no} is {type(obj).__name__}, expected object.\n"
                    + _format_hint(path)
                )
            if "id" not in obj and "answer_text" not in obj:
                raise ValueError(
                    f"Invalid JSONL: line {line_no} must include at least 'id' or 'answer_text'.\n"
                    + _format_hint(path)
                )
            rows.append(obj)

    if not rows:
        raise ValueError("Input file is empty or has no JSONL rows.\n" + _format_hint(path))
    return rows


def shorten(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def line_hit(answer: str, fact: str) -> bool:
    ans = (answer or "").lower()
    return all(token in ans for token in fact.lower().split() if len(token) > 2)


def extract_scoring_text(row: Dict[str, Any]) -> tuple[str, str]:
    """Prefer visual evidence OCR/structured fields, fallback to answer_text."""
    raw_response = row.get("raw_response")
    if isinstance(raw_response, dict):
        visual_evidence = raw_response.get("visual_evidence")
        if isinstance(visual_evidence, list) and visual_evidence:
            pieces: list[str] = []
            for ev in visual_evidence:
                if not isinstance(ev, dict):
                    continue
                for key in ("ocr_text", "summary", "task_type"):
                    value = ev.get(key)
                    if isinstance(value, str) and value.strip():
                        pieces.append(value.strip())
            if pieces:
                return "\n".join(pieces), "visual_evidence"
    return row.get("answer_text", "") or "", "answer_text"


def render_case(row: Dict[str, Any], answer_limit: int) -> None:
    case_id = row.get("id", "unknown")
    latency = row.get("latency_ms")
    error = row.get("error")
    answer, scored_from = extract_scoring_text(row)
    gold = row.get("golden_facts", []) or []
    neg = row.get("negative_facts", []) or []

    print("=" * 120)
    print(f"CASE: {case_id} | latency={latency}ms | error={bool(error)} | scored_from={scored_from}")
    if error:
        print(f"ERROR: {error}")

    print("-" * 120)
    print("EXPECTED GOLDEN FACTS  <->  ACTUAL ANSWER")
    print("-" * 120)

    if not gold:
        print("(no golden facts)")
    else:
        for i, fact in enumerate(gold, 1):
            status = "✓" if line_hit(answer, fact) else "✗"
            print(f"[{status}] G{i:02d}: {fact}")

    print("-" * 120)
    print("NEGATIVE FACTS (should be absent)")
    if not neg:
        print("(no negative facts)")
    else:
        for i, fact in enumerate(neg, 1):
            violated = line_hit(answer, fact)
            mark = "⚠" if violated else "✓"
            verdict = "present" if violated else "absent"
            print(f"[{mark}] N{i:02d}: {fact} -> {verdict}")

    print("-" * 120)
    print("ACTUAL ANSWER:")
    print(shorten(answer, answer_limit) or "(empty)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show expected vs actual VLM recognition side-by-side in console.")
    parser.add_argument("--input", required=True, help="Path to vlm_*_results.jsonl")
    parser.add_argument("--case", help="Optional case id filter (e.g. img05_chart_sales_q)")
    parser.add_argument("--answer-limit", type=int, default=1000, help="Max answer chars to print")
    args = parser.parse_args()

    try:
        rows = load_jsonl(Path(args.input))
    except ValueError as exc:
        raise SystemExit(f"Input format error: {exc}")
    if args.case:
        rows = [r for r in rows if r.get("id") == args.case]

    if not rows:
        print("No cases to display.")
        return

    print(f"Loaded cases: {len(rows)} from {args.input}")
    for row in rows:
        render_case(row, args.answer_limit)


if __name__ == "__main__":
    main()
