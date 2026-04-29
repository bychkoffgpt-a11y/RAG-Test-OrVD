#!/usr/bin/env python3
import argparse
import time
from datetime import datetime

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True)
    ap.add_argument("--image-url", required=True)
    ap.add_argument("--question", default="Опиши ключевые визуальные факты изображения. Не выдумывай.")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    for i in range(1, args.runs + 1):
        payload = {"question": args.question, "images": [args.image_url]}
        t0 = time.time()
        err = None
        resp_json = None
        status = None

        try:
            r = requests.post(f"{args.api_url.rstrip('/')}/ask", json=payload, timeout=args.timeout)
            status = r.status_code
            resp_json = r.json()
        except Exception as e:
            err = str(e)

        dt = int((time.time() - t0) * 1000)
        print(f"\n=== RUN {i} @ {datetime.utcnow().isoformat()}Z ===")
        print("status:", status)
        print("latency_ms:", dt)
        print("error:", err)

        if isinstance(resp_json, dict):
            answer = resp_json.get("answer") or resp_json.get("text") or resp_json.get("output_text")
            visual_evidence = resp_json.get("visual_evidence")
            images = resp_json.get("images")
            sources = resp_json.get("sources")
            print("answer_preview:", (answer[:300] + "...") if isinstance(answer, str) and len(answer) > 300 else answer)
            print("visual_evidence_type:", type(visual_evidence).__name__)
            print("visual_evidence_len:", len(visual_evidence) if isinstance(visual_evidence, list) else None)
            print("images_type:", type(images).__name__)
            print("images_len:", len(images) if isinstance(images, list) else None)
            print("sources_len:", len(sources) if isinstance(sources, list) else None)
            print("raw_keys:", sorted(resp_json.keys()))
        else:
            print("raw_response:", resp_json)


if __name__ == "__main__":
    main()
