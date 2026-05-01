#!/usr/bin/env python3
import json
import time
import argparse
import requests
from pathlib import Path

SYSTEM_PROMPT = "Ты аккуратный VLM-ассистент. Не выдумывай. Если не видно, так и скажи."
USER_TEXT = (
    "Опиши изображение 4-6 конкретными фактами, "
    "потом отдельно пунктом напиши, что не удалось надёжно распознать."
)

def call_chat(api_url: str, model: str, image_url: str, rag_scope: str, timeout: int = 120):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_TEXT},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        "temperature": 0.0,
        "rag_scope": rag_scope,
    }
    r = requests.post(f"{api_url.rstrip('/')}/v1/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def extract_text(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(resp, ensure_ascii=False)


def enrich_runtime_fields(row: dict, resp: dict | None) -> None:
    raw = resp if isinstance(resp, dict) else {}
    visual = raw.get("visual_evidence") if isinstance(raw.get("visual_evidence"), list) else []
    nonempty_ocr_count = sum(
        1 for ev in visual
        if isinstance(ev, dict) and isinstance(ev.get("ocr_text"), str) and ev.get("ocr_text").strip()
    )
    row["visual_evidence_count"] = len(visual)
    row["nonempty_ocr_count"] = nonempty_ocr_count
    row["answer_len"] = len((row.get("answer_text") or "").strip())
    row["json_parse_status"] = "ok" if isinstance(resp, dict) else "not_json"
    row["fallback_used"] = bool(raw.get("fallback_used")) if isinstance(resp, dict) else False
    row["task_type_detected"] = ""
    for ev in visual:
        if isinstance(ev, dict) and isinstance(ev.get("task_type"), str) and ev.get("task_type").strip():
            row["task_type_detected"] = ev.get("task_type").strip()
            break

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="например http://localhost:8000")
    ap.add_argument("--model", default="local-vlm")
    ap.add_argument("--cases", default="vlm_test_cases.json")
    ap.add_argument("--out", default="vlm_chat_results.jsonl")
    ap.add_argument("--rag-scope", default="none", help="RAG scope для /v1/chat/completions: all|csv_ans_docs|internal_regulations|none")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    out = Path(args.out)

    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            started = time.time()
            err = None
            resp = None
            try:
                resp = call_chat(args.api_url, args.model, c["url"], args.rag_scope)
                text = extract_text(resp)
            except Exception as e:
                text = ""
                err = str(e)
            latency_ms = int((time.time() - started) * 1000)

            row = {
                "id": c["id"],
                "url": c["url"],
                "golden_facts": c["golden_facts"],
                "negative_facts": c["negative_facts"],
                "latency_ms": latency_ms,
                "error": err,
                "answer_text": text,
                "raw_response": resp
            }
            enrich_runtime_fields(row, resp)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{c['id']}] latency={latency_ms}ms error={err is not None}")
            time.sleep(args.sleep)

    print(f"\nSaved: {out}")

if __name__ == "__main__":
    main()
