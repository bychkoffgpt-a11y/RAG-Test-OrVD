#!/usr/bin/env python3
import argparse
import json
import re
import csv
import statistics
from pathlib import Path
from typing import List, Dict, Any

def normalize_text(s: str) -> str:
    s = s.lower()
    s = s.replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fact_to_keywords(fact: str) -> List[str]:
    """
    Простое извлечение 'якорных' токенов из факта.
    Пример: 'Есть дата 2026-05-15' -> ['2026-05-15']
    """
    f = normalize_text(fact)
    # токены: слова/числа/даты/символы типа c-7, a-1024
    tokens = re.findall(r"[a-zа-я0-9\-:\.%$]+", f, flags=re.IGNORECASE)
    # убираем слишком короткие и шумовые
    stop = {"есть", "на", "и", "в", "по", "это", "как", "для", "из", "the", "is", "a", "an", "of"}
    tokens = [t for t in tokens if len(t) >= 2 and t not in stop]
    # оставляем уникальные в порядке
    uniq = []
    seen = set()
    for t in tokens:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:8]

def match_fact(answer_norm: str, fact: str) -> bool:
    """
    Факт засчитан, если в ответе есть >=1-2 ключевых токена факта:
    - для коротких фактов: >=1 токен
    - для длинных: >=2 токена
    """
    kws = fact_to_keywords(fact)
    if not kws:
        return False
    hits = sum(1 for k in kws if k in answer_norm)
    need = 1 if len(kws) <= 2 else 2
    return hits >= need

def detect_negative_hit(answer_norm: str, neg_fact: str) -> bool:
    """
    Если негативный факт 'матчится', считаем это потенциальной галлюцинацией.
    """
    return match_fact(answer_norm, neg_fact)

def parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                rows.append({
                    "id": f"line_{i}",
                    "error": f"JSON parse error: {e}",
                    "answer_text": "",
                    "golden_facts": [],
                    "negative_facts": [],
                    "latency_ms": None,
                })
    return rows

def percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    k = (len(values) - 1) * p
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[int(k)]
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1

def score_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_case = []
    latencies = []
    total_golden = 0
    total_golden_hit = 0
    total_neg = 0
    total_neg_hit = 0
    errors = 0

    for r in rows:
        case_id = r.get("id", "unknown")
        err = r.get("error")
        if err:
            errors += 1

        answer = r.get("answer_text") or ""
        answer_norm = normalize_text(answer)

        golden = r.get("golden_facts") or []
        negative = r.get("negative_facts") or []
        latency = r.get("latency_ms")
        if isinstance(latency, (int, float)):
            latencies.append(float(latency))

        golden_hits = 0
        golden_missed = []
        for gf in golden:
            if match_fact(answer_norm, gf):
                golden_hits += 1
            else:
                golden_missed.append(gf)

        neg_hits = 0
        neg_triggered = []
        for nf in negative:
            if detect_negative_hit(answer_norm, nf):
                neg_hits += 1
                neg_triggered.append(nf)

        total_golden += len(golden)
        total_golden_hit += golden_hits
        total_neg += len(negative)
        total_neg_hit += neg_hits

        recall = (golden_hits / len(golden)) if golden else 0.0
        halluc_rate = (neg_hits / len(negative)) if negative else 0.0

        per_case.append({
            "id": case_id,
            "latency_ms": latency,
            "golden_total": len(golden),
            "golden_hit": golden_hits,
            "golden_recall": round(recall, 4),
            "neg_total": len(negative),
            "neg_hit": neg_hits,
            "hallucination_rate": round(halluc_rate, 4),
            "error": err or "",
            "golden_missed": " | ".join(golden_missed),
            "negative_triggered": " | ".join(neg_triggered),
        })

    macro_recall = (total_golden_hit / total_golden) if total_golden else 0.0
    halluc_overall = (total_neg_hit / total_neg) if total_neg else 0.0

    summary = {
        "cases_total": len(rows),
        "cases_with_error": errors,
        "golden_total": total_golden,
        "golden_hit": total_golden_hit,
        "macro_recall": round(macro_recall, 4),
        "negative_total": total_neg,
        "negative_hit": total_neg_hit,
        "hallucination_rate": round(halluc_overall, 4),
        "latency_p50_ms": round(percentile(latencies, 0.50), 2) if latencies else None,
        "latency_p95_ms": round(percentile(latencies, 0.95), 2) if latencies else None,
        "latency_mean_ms": round(statistics.mean(latencies), 2) if latencies else None,
    }
    return {"summary": summary, "per_case": per_case}

def write_csv(per_case: List[Dict[str, Any]], out_csv: Path):
    cols = [
        "id", "latency_ms",
        "golden_total", "golden_hit", "golden_recall",
        "neg_total", "neg_hit", "hallucination_rate",
        "error", "golden_missed", "negative_triggered"
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in per_case:
            w.writerow({k: row.get(k, "") for k in cols})

def main():
    ap = argparse.ArgumentParser(description="Score VLM JSONL results")
    ap.add_argument("--input", required=True, help="JSONL results file")
    ap.add_argument("--out-json", default="vlm_score_summary.json", help="Summary JSON output")
    ap.add_argument("--out-csv", default="vlm_score_per_case.csv", help="Per-case CSV output")
    args = ap.parse_args()

    rows = parse_jsonl(Path(args.input))
    report = score_rows(rows)

    Path(args.out_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    write_csv(report["per_case"], Path(args.out_csv))

    s = report["summary"]
    print("=== VLM SCORE SUMMARY ===")
    print(f"Input file          : {args.input}")
    print(f"Cases total         : {s['cases_total']}")
    print(f"Cases with error    : {s['cases_with_error']}")
    print(f"Golden recall       : {s['macro_recall']:.4f} ({s['golden_hit']}/{s['golden_total']})")
    print(f"Hallucination rate  : {s['hallucination_rate']:.4f} ({s['negative_hit']}/{s['negative_total']})")
    print(f"Latency p50 (ms)    : {s['latency_p50_ms']}")
    print(f"Latency p95 (ms)    : {s['latency_p95_ms']}")
    print(f"Latency mean (ms)   : {s['latency_mean_ms']}")
    print(f"Saved summary JSON  : {args.out_json}")
    print(f"Saved per-case CSV  : {args.out_csv}")

if __name__ == "__main__":
    main()
