#!/usr/bin/env python3
import json
import time
import argparse
import requests
from pathlib import Path

DEFAULT_PROMPT = (
    "Проанализируй изображение, распознай весь текст, "
    "опиши картинки и графические изображения."
)


def call_vision_debug(api_url: str, prompt: str, image_url: str, max_tokens: int, temperature: float, timeout: int = 120):
    payload = {
        "prompt": prompt,
        "attachments": [{"image_path": image_url}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(f"{api_url.rstrip('/')}/vision/debug/recognize", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def extract_text(resp: dict) -> str:
    if isinstance(resp, dict) and isinstance(resp.get("answer"), str):
        return resp["answer"]
    return json.dumps(resp, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="например http://localhost:8000")
    ap.add_argument("--cases", default="vlm_test_cases.json")
    ap.add_argument("--out", default="vlm_vision_debug_results.jsonl")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.0)
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
                resp = call_vision_debug(args.api_url, args.prompt, c["url"], args.max_tokens, args.temperature)
                text = extract_text(resp)
            except Exception as e:
                text = ""
                err = str(e)
            latency_ms = int((time.time() - started) * 1000)

            row = {
                "id": c["id"],
                "url": c["url"],
                "task_type": c.get("task_type"),
                "golden_facts": c["golden_facts"],
                "negative_facts": c["negative_facts"],
                "latency_ms": latency_ms,
                "error": err,
                "answer_text": text,
                "raw_response": resp,
            }
            visual = (resp or {}).get("visual_evidence") if isinstance(resp, dict) else None
            if isinstance(visual, list) and visual:
                row["task_type_routed"] = (visual[0] or {}).get("task_type")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{c['id']}] latency={latency_ms}ms error={err is not None}")
            time.sleep(args.sleep)

    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
