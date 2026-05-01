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
    ap = argparse.ArgumentParser(description="Compare /ask, /chat и /vision/debug/recognize VLM diagnostics summaries")
    ap.add_argument("--ask-summary", required=True)
    ap.add_argument("--chat-summary", required=True)
    ap.add_argument("--vision-summary")
    ap.add_argument("--git-sha")
    ap.add_argument("--git-branch")
    ap.add_argument("--out-markdown", default="comparison.md")
    args = ap.parse_args()

    ask = load(Path(args.ask_summary))
    chat = load(Path(args.chat_summary))
    vision = load(Path(args.vision_summary)) if args.vision_summary else {}

    ask_s = ask.get("summary", {})
    chat_s = chat.get("summary", {})

    lines = [
        "# VLM diagnostics comparison",
        "",
        "## Run metadata",
        "",
        f"- Git SHA: `{args.git_sha or 'n/a'}`",
        f"- Git branch: `{args.git_branch or 'n/a'}`",
        "",
        "## Overall",
        "",
        "| Metric | /ask | /v1/chat/completions | /vision/debug/recognize | Delta (chat-ask) |",
        "|---|---:|---:|---:|---:|",
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
        vv = (vision.get("summary") or {}).get(m) if vision else None
        delta = (cv - av) if isinstance(av, (int, float)) and isinstance(cv, (int, float)) else None
        lines.append(f"| {m} | {fmt(av)} | {fmt(cv)} | {fmt(vv)} | {fmt(delta)} |")

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

    def endpoint_taxonomy(name: str, summary: dict) -> list[str]:
        reasons = [
            ("empty answers", summary.get("empty_answer_cases", 0), summary.get("empty_answers_pct")),
            ("visual_evidence without ocr", summary.get("visual_without_ocr_cases", 0), summary.get("visual_without_ocr_pct")),
            ("parse_fail", summary.get("parse_fail_cases", 0), summary.get("parse_fail_pct")),
        ]
        reasons = sorted(reasons, key=lambda x: x[1], reverse=True)[:3]
        out = [f"### {name}"]
        for label, count, pct in reasons:
            out.append(f"- {label}: {count} cases ({fmt(pct)}%)")
        return out

    lines.extend(["", "## Failure taxonomy", ""])
    lines.extend(endpoint_taxonomy("/ask", ask_s))
    lines.extend([""])
    lines.extend(endpoint_taxonomy("/v1/chat/completions", chat_s))
    if vision:
        lines.extend([""])
        lines.extend(endpoint_taxonomy("/vision/debug/recognize", vision.get("summary") or {}))

    Path(args.out_markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved: {args.out_markdown}")


if __name__ == "__main__":
    main()
