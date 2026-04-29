#!/usr/bin/env python3
import json
import time
import argparse
import requests
from pathlib import Path

DEFAULT_PROMPT = (
    "Ты проверяешь визуальное распознавание. "
    "1) Перечисли 4-6 конкретных визуальных фактов. "
    "2) Явно укажи, что НЕ видно/нечитаемо. "
    "3) Не выдумывай факты."
)

def call_ask(api_url: str, question: str, image_url: str, timeout: int = 90):
    # Подстрой под ваш фактический контракт /ask при необходимости
    payload = {
        "question": question,
        "images": [image_url]
    }
    r = requests.post(f"{api_url.rstrip('/')}/ask", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def extract_text(resp: dict) -> str:
    # Универсально: подстраховка под разные варианты ответа
    if isinstance(resp, dict):
        for k in ("answer", "output_text", "text", "response"):
            if k in resp and isinstance(resp[k], str):
                return resp[k]
    return json.dumps(resp, ensure_ascii=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="например http://localhost:8000")
    ap.add_argument("--cases", default="vlm_test_cases.json")
    ap.add_argument("--out", default="vlm_ask_results.jsonl")
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
                resp = call_ask(args.api_url, DEFAULT_PROMPT, c["url"])
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
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{c['id']}] latency={latency_ms}ms error={err is not None}")
            time.sleep(args.sleep)

    print(f"\nSaved: {out}")

if __name__ == "__main__":
    main()