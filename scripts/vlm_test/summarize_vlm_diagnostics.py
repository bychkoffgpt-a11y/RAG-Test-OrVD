#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def main():
    ap = argparse.ArgumentParser(description="Compare /ask and /chat VLM diagnostics summaries")
    ap.add_argument("--ask-summary", required=True)
    ap.add_argument("--chat-summary", required=True)
    ap.add_argument("--out-markdown", default="comparison.md")
    args = ap.parse_args()

    ask = load(Path(args.ask_summary))
    chat = load(Path(args.chat_summary))

    ask_s = ask.get("summary", {})
    chat_s = chat.get("summary", {})

    lines = [
        "# VLM diagnostics comparison",
        "",
        "## Overall",
        "",
        "| Metric | /ask | /v1/chat/completions | Delta (chat-ask) |",
        "|---|---:|---:|---:|",
    ]

    metrics = [
        "golden_hard_recall",
        "golden_partial_recall",
        "hallucination_hard_rate",
        "hallucination_partial_rate",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_mean_ms",
    ]
    for m in metrics:
        av = ask_s.get(m)
        cv = chat_s.get(m)
        delta = (cv - av) if isinstance(av, (int, float)) and isinstance(cv, (int, float)) else None
        lines.append(f"| {m} | {fmt(av)} | {fmt(cv)} | {fmt(delta)} |")

    lines.extend(["", "## Group-level", ""])
    lines.append("| Group | Metric | /ask | /chat | Delta |")
    lines.append("|---|---|---:|---:|---:|")

    groups = sorted(set((ask.get("groups") or {}).keys()) | set((chat.get("groups") or {}).keys()))
    group_metrics = [
        "golden_hard_recall",
        "golden_partial_recall",
        "hallucination_hard_rate",
        "hallucination_partial_rate",
        "latency_p50_ms",
        "latency_p95_ms",
    ]
    for g in groups:
        ag = (ask.get("groups") or {}).get(g, {})
        cg = (chat.get("groups") or {}).get(g, {})
        for m in group_metrics:
            av = ag.get(m)
            cv = cg.get(m)
            delta = (cv - av) if isinstance(av, (int, float)) and isinstance(cv, (int, float)) else None
            lines.append(f"| {g} | {m} | {fmt(av)} | {fmt(cv)} | {fmt(delta)} |")

    lines.extend([
        "",
        "## Interpretation hints",
        "",
        "- `golden_partial_recall` near zero for `/ask` with non-zero for `/chat` usually means image path is broken in `/ask` pipeline.",
        "- Higher recall with sharply higher hallucination rate at lower threshold implies unstable semantic grounding.",
        "- `latency_p95_ms` gap helps detect heavy VLM processing or retries in one endpoint only.",
    ])

    Path(args.out_markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved: {args.out_markdown}")


if __name__ == "__main__":
    main()
