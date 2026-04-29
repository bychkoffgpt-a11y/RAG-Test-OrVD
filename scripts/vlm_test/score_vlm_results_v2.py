#!/usr/bin/env python3
import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(s: str) -> List[str]:
    s = norm(s)
    return re.findall(r"[a-zа-я0-9\-\+\.:/%$]+", s, flags=re.IGNORECASE)


DEFAULT_ALIASES = {
    "stop": ["stop", "стоп"],
    "sign": ["sign", "знак", "табличка", "указатель"],
    "warning": ["warning", "предупреждение", "внимание"],
    "high voltage": ["high voltage", "высокое напряжение"],
    "invoice": ["invoice", "инвойс", "счет", "счёт"],
    "error": ["error", "ошибка"],
    "service unavailable": ["service unavailable", "сервис недоступен", "недоступен"],
    "chart": ["chart", "diagram", "диаграмма", "график"],
    "bar": ["bar", "столбчат", "гистограмм"],
    "line": ["line", "линейн"],
    "pie": ["pie", "кругов"],
    "largest": ["largest", "biggest", "самый большой", "наибольший", "максимальный"],
    "smallest": ["smallest", "least", "самый маленький", "минимальный", "наименьший"],
    "right": ["right", "вправо", "справа"],
    "left": ["left", "влево", "слева"],
    "text": ["text", "текст", "надпись"],
    "table": ["table", "таблица", "табличн", "csv"],
    "open": ["open", "открыт", "открыто"],
    "meeting": ["meeting", "встреча", "митинг"],
}

STOPWORDS = {
    "есть", "это", "на", "в", "и", "по", "с", "как", "для", "из", "что", "ли", "не", "нет",
    "the", "is", "a", "an", "of", "to", "in", "on", "and", "or", "with", "by", "as", "it",
}

NUMERIC_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def load_aliases(path: str = None) -> Dict[str, List[str]]:
    aliases = dict(DEFAULT_ALIASES)
    if path:
        p = Path(path)
        if p.exists():
            user_aliases = json.loads(p.read_text(encoding="utf-8"))
            for k, v in user_aliases.items():
                base = aliases.get(k, [])
                aliases[k] = list(dict.fromkeys(base + list(v)))
    return aliases


def extract_anchors(fact: str) -> List[str]:
    f = norm(fact)
    anchors = []
    anchors += DATE_RE.findall(f)
    anchors += NUMERIC_RE.findall(f)

    toks = tokenize(f)
    for t in toks:
        if len(t) < 2:
            continue
        if t in STOPWORDS:
            continue
        anchors.append(t)

    out, seen = [], set()
    for a in anchors:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:12]


def expand_anchor(anchor: str, aliases: Dict[str, List[str]]) -> List[str]:
    a = norm(anchor)
    variants = {a}

    if a in aliases:
        variants.update(norm(x) for x in aliases[a])

    for key, vals in aliases.items():
        vals_norm = [norm(x) for x in vals]
        if a == norm(key) or a in vals_norm:
            variants.add(norm(key))
            variants.update(vals_norm)

    if a.startswith("столбчат"):
        variants.update(["bar", "столбчат", "гистограмм"])
    if a.startswith("линейн"):
        variants.update(["line", "линейн"])
    if a.startswith("кругов"):
        variants.update(["pie", "кругов"])

    return sorted(variants)


def text_contains_any(answer: str, variants: List[str]) -> bool:
    ans = norm(answer)
    return any(v and v in ans for v in variants)


def score_fact_partial(answer: str, fact: str, aliases: Dict[str, List[str]]) -> Tuple[float, Dict[str, Any]]:
    anchors = extract_anchors(fact)
    if not anchors:
        return 0.0, {"anchors": [], "matched": [], "ratio": 0.0}

    matched = []
    for a in anchors:
        vars_ = expand_anchor(a, aliases)
        if text_contains_any(answer, vars_):
            matched.append(a)

    ratio = len(matched) / len(anchors)

    strong = [x for x in anchors if DATE_RE.fullmatch(x) or NUMERIC_RE.fullmatch(x)]
    strong_matched = any(x in matched for x in strong)
    if strong and strong_matched and ratio < 0.35:
        ratio = 0.35

    return max(0.0, min(1.0, ratio)), {"anchors": anchors, "matched": matched, "ratio": ratio}


def classify_group(case_id: str, url: str) -> str:
    s = norm(case_id + " " + (url or ""))
    if any(k in s for k in ["chart", "quickchart", "pie", "line_trend", "sales_q", "compare_ab"]):
        return "chart"
    if any(k in s for k in ["sign", "warning", "exit", "stop"]):
        return "sign"
    if any(k in s for k in ["invoice", "table", "note", "meeting", "error_banner", "multiline", "text"]):
        return "text"
    return "other"


def percentile(vals: List[float], p: float) -> float:
    if not vals:
        return float("nan")
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                rows.append({
                    "id": f"line_{i}",
                    "error": f"JSON parse error: {e}",
                    "answer_text": "",
                    "golden_facts": [],
                    "negative_facts": [],
                    "latency_ms": None,
                    "url": "",
                })
    return rows


def score(rows: List[Dict[str, Any]], aliases: Dict[str, List[str]], hit_threshold: float = 0.6) -> Dict[str, Any]:
    per_case = []
    lat = []
    by_group = {}

    total_gold = 0
    total_gold_hard_hits = 0
    total_gold_partial_sum = 0.0
    total_neg = 0
    total_neg_hard_hits = 0
    total_neg_partial_sum = 0.0
    errors = 0

    for r in rows:
        cid = r.get("id", "unknown")
        url = r.get("url", "")
        grp = classify_group(cid, url)

        ans = r.get("answer_text") or ""
        err = r.get("error")
        if err:
            errors += 1

        latency = r.get("latency_ms")
        if isinstance(latency, (int, float)):
            lat.append(float(latency))

        golden = r.get("golden_facts") or []
        negative = r.get("negative_facts") or []

        gold_scores, gold_hard, gold_details = [], 0, []
        for gf in golden:
            sc, det = score_fact_partial(ans, gf, aliases)
            gold_scores.append(sc)
            if sc >= hit_threshold:
                gold_hard += 1
            gold_details.append({"fact": gf, "score": round(sc, 4), "matched": det["matched"], "anchors": det["anchors"]})

        neg_scores, neg_hard, neg_details = [], 0, []
        for nf in negative:
            sc, det = score_fact_partial(ans, nf, aliases)
            neg_scores.append(sc)
            if sc >= hit_threshold:
                neg_hard += 1
            neg_details.append({"fact": nf, "score": round(sc, 4), "matched": det["matched"], "anchors": det["anchors"]})

        case_gold_partial = (sum(gold_scores) / len(golden)) if golden else 0.0
        case_gold_hard_recall = (gold_hard / len(golden)) if golden else 0.0
        case_neg_partial = (sum(neg_scores) / len(negative)) if negative else 0.0
        case_neg_hard = (neg_hard / len(negative)) if negative else 0.0

        per_case.append({
            "id": cid,
            "group": grp,
            "latency_ms": latency,
            "error": err or "",
            "golden_total": len(golden),
            "golden_hard_hits": gold_hard,
            "golden_hard_recall": round(case_gold_hard_recall, 4),
            "golden_partial_recall": round(case_gold_partial, 4),
            "negative_total": len(negative),
            "negative_hard_hits": neg_hard,
            "hallucination_hard_rate": round(case_neg_hard, 4),
            "hallucination_partial_rate": round(case_neg_partial, 4),
            "golden_details_json": json.dumps(gold_details, ensure_ascii=False),
            "negative_details_json": json.dumps(neg_details, ensure_ascii=False),
        })

        total_gold += len(golden)
        total_gold_hard_hits += gold_hard
        total_gold_partial_sum += sum(gold_scores)
        total_neg += len(negative)
        total_neg_hard_hits += neg_hard
        total_neg_partial_sum += sum(neg_scores)

        g = by_group.setdefault(grp, {
            "cases": 0,
            "gold_total": 0, "gold_hard": 0, "gold_partial_sum": 0.0,
            "neg_total": 0, "neg_hard": 0, "neg_partial_sum": 0.0,
            "lat": [],
        })
        g["cases"] += 1
        g["gold_total"] += len(golden)
        g["gold_hard"] += gold_hard
        g["gold_partial_sum"] += sum(gold_scores)
        g["neg_total"] += len(negative)
        g["neg_hard"] += neg_hard
        g["neg_partial_sum"] += sum(neg_scores)
        if isinstance(latency, (int, float)):
            g["lat"].append(float(latency))

    summary = {
        "cases_total": len(rows),
        "cases_with_error": errors,
        "golden_total": total_gold,
        "golden_hard_hits": total_gold_hard_hits,
        "golden_hard_recall": round((total_gold_hard_hits / total_gold) if total_gold else 0.0, 4),
        "golden_partial_recall": round((total_gold_partial_sum / total_gold) if total_gold else 0.0, 4),
        "negative_total": total_neg,
        "negative_hard_hits": total_neg_hard_hits,
        "hallucination_hard_rate": round((total_neg_hard_hits / total_neg) if total_neg else 0.0, 4),
        "hallucination_partial_rate": round((total_neg_partial_sum / total_neg) if total_neg else 0.0, 4),
        "latency_p50_ms": round(percentile(lat, 0.50), 2) if lat else None,
        "latency_p95_ms": round(percentile(lat, 0.95), 2) if lat else None,
        "latency_mean_ms": round(statistics.mean(lat), 2) if lat else None,
    }

    groups = {}
    for grp, g in by_group.items():
        groups[grp] = {
            "cases": g["cases"],
            "golden_hard_recall": round((g["gold_hard"] / g["gold_total"]) if g["gold_total"] else 0.0, 4),
            "golden_partial_recall": round((g["gold_partial_sum"] / g["gold_total"]) if g["gold_total"] else 0.0, 4),
            "hallucination_hard_rate": round((g["neg_hard"] / g["neg_total"]) if g["neg_total"] else 0.0, 4),
            "hallucination_partial_rate": round((g["neg_partial_sum"] / g["neg_total"]) if g["neg_total"] else 0.0, 4),
            "latency_p50_ms": round(percentile(g["lat"], 0.50), 2) if g["lat"] else None,
            "latency_p95_ms": round(percentile(g["lat"], 0.95), 2) if g["lat"] else None,
        }

    return {"summary": summary, "groups": groups, "per_case": per_case}


def write_csv(per_case: List[Dict[str, Any]], path: Path):
    cols = [
        "id", "group", "latency_ms", "error",
        "golden_total", "golden_hard_hits", "golden_hard_recall", "golden_partial_recall",
        "negative_total", "negative_hard_hits", "hallucination_hard_rate", "hallucination_partial_rate",
        "golden_details_json", "negative_details_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in per_case:
            w.writerow({k: r.get(k, "") for k in cols})


def main():
    ap = argparse.ArgumentParser(description="VLM scorer v2 with aliases + partial credit + group metrics")
    ap.add_argument("--input", required=True, help="JSONL results file")
    ap.add_argument("--out-json", default="vlm_score_v2_summary.json", help="summary JSON output")
    ap.add_argument("--out-csv", default="vlm_score_v2_per_case.csv", help="per-case CSV output")
    ap.add_argument("--aliases", default=None, help="optional aliases JSON file")
    ap.add_argument("--hit-threshold", type=float, default=0.6, help="score >= threshold counts as hard hit")
    args = ap.parse_args()

    rows = parse_jsonl(Path(args.input))
    aliases = load_aliases(args.aliases)
    report = score(rows, aliases=aliases, hit_threshold=args.hit_threshold)

    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report["per_case"], Path(args.out_csv))

    s = report["summary"]
    print("=== VLM SCORE SUMMARY v2 ===")
    print(f"Input file                  : {args.input}")
    print(f"Cases total                 : {s['cases_total']}")
    print(f"Cases with error            : {s['cases_with_error']}")
    print(f"Golden hard recall          : {s['golden_hard_recall']:.4f} ({s['golden_hard_hits']}/{s['golden_total']})")
    print(f"Golden partial recall       : {s['golden_partial_recall']:.4f}")
    print(f"Hallucination hard rate     : {s['hallucination_hard_rate']:.4f} ({s['negative_hard_hits']}/{s['negative_total']})")
    print(f"Hallucination partial rate  : {s['hallucination_partial_rate']:.4f}")
    print(f"Latency p50 (ms)            : {s['latency_p50_ms']}")
    print(f"Latency p95 (ms)            : {s['latency_p95_ms']}")
    print(f"Latency mean (ms)           : {s['latency_mean_ms']}")

    print("\n=== BY GROUP ===")
    for g, m in sorted(report["groups"].items()):
        print(
            f"[{g}] cases={m['cases']}, "
            f"gold_hard={m['golden_hard_recall']:.4f}, gold_partial={m['golden_partial_recall']:.4f}, "
            f"hall_hard={m['hallucination_hard_rate']:.4f}, hall_partial={m['hallucination_partial_rate']:.4f}, "
            f"p50={m['latency_p50_ms']}, p95={m['latency_p95_ms']}"
        )

    print(f"\nSaved summary JSON          : {args.out_json}")
    print(f"Saved per-case CSV          : {args.out_csv}")


if __name__ == "__main__":
    main()
