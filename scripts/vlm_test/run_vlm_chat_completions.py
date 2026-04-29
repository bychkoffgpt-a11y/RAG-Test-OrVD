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

def call_chat(api_url: str, model: str, image_url: str, timeout: int = 120):
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
        "temperature": 0.0
    }
    r = requests.post(f"{api_url.rstrip('/')}/v1/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def extract_text(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(resp, ensure_ascii=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="например http://localhost:8000")
    ap.add_argument("--model", default="local-vlm")
    ap.add_argument("--cases", default="vlm_test_cases.json")
    ap.add_argument("--out", default="vlm_chat_results.jsonl")
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
                resp = call_chat(args.api_url, args.model, c["url"])
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