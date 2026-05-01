#!/usr/bin/env python3
import json
import time
import argparse
import requests
from pathlib import Path

DEFAULT_PROMPT_MODE = "json_strict"

JSON_STRICT_PROMPT = (
    "Ты — модуль визуального анализа для runtime-контура поддержки. "
    "Верни только JSON-объект строго следующей структуры: "
    "{\"visible_facts\":[string],\"uncertain_facts\":[string],\"not_visible\":[string],\"confidence\":number}. "
    "Правила: visible_facts — только факты, явно подтверждаемые изображением; "
    "uncertain_facts — вероятные, но не полностью подтверждённые наблюдения; "
    "not_visible — факты, которые нельзя проверить по изображению; "
    "confidence — число от 0 до 1 для общей уверенности распознавания. "
    "Не добавляй никакой текст вне JSON и не придумывай детали, которых нет на изображении."
)

FREEFORM_PROMPT = (
    "Проанализируй изображение, распознай весь текст, опиши картинки и графические изображения."
)


def build_prompt(prompt_mode: str, prompt_override: str | None) -> str:
    if prompt_override:
        return prompt_override
    if prompt_mode == "freeform":
        return FREEFORM_PROMPT
    return JSON_STRICT_PROMPT


def call_vision_debug(api_url: str, prompt: str, image_url: str, max_tokens: int, temperature: float, task_type: str | None = None, timeout: int = 120):
    payload = {
        "prompt": prompt,
        "attachments": [{"image_path": image_url}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if task_type:
        payload["task_type"] = task_type
    r = requests.post(f"{api_url.rstrip('/')}/vision/debug/recognize", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def extract_text(resp: dict) -> str:
    if isinstance(resp, dict) and isinstance(resp.get("answer"), str):
        return resp["answer"]
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
    ap.add_argument("--cases", default="vlm_test_cases.json")
    ap.add_argument("--out", default="vlm_vision_debug_results.jsonl")
    ap.add_argument("--prompt-mode", choices=["json_strict", "freeform"], default=DEFAULT_PROMPT_MODE,
                    help="Режим промпта: json_strict (runtime-совместимый JSON) или freeform (свободный ответ)")
    ap.add_argument("--prompt", default=None,
                    help="Явный prompt-override. Если задан, --prompt-mode игнорируется")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    if args.prompt_mode == "freeform":
        print("[WARN] prompt_mode=freeform: scoring по golden_facts может деградировать из-за неструктурированного ответа.")

    prompt = build_prompt(args.prompt_mode, args.prompt)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    out = Path(args.out)

    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            started = time.time()
            err = None
            resp = None
            try:
                resp = call_vision_debug(
                    args.api_url,
                    prompt,
                    c["url"],
                    args.max_tokens,
                    args.temperature,
                    c.get("task_type"),
                )
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
            enrich_runtime_fields(row, resp)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{c['id']}] latency={latency_ms}ms error={err is not None}")
            time.sleep(args.sleep)

    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
