#!/usr/bin/env python3
"""Console face-off view: expected vs actual facts for VLM runs."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                rows.append({"id": f"line_{line_no}", "error": f"json decode error: {exc}"})
    return rows


def shorten(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def line_hit(answer: str, fact: str) -> bool:
    ans = (answer or "").lower()
    return all(token in ans for token in fact.lower().split() if len(token) > 2)


def render_case(row: Dict[str, Any], answer_limit: int) -> None:
    case_id = row.get("id", "unknown")
    latency = row.get("latency_ms")
    error = row.get("error")
    answer = row.get("answer_text", "")
    gold = row.get("golden_facts", []) or []
    neg = row.get("negative_facts", []) or []

    print("=" * 120)
    print(f"CASE: {case_id} | latency={latency}ms | error={bool(error)}")
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

    rows = load_jsonl(Path(args.input))
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
