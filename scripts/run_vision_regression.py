#!/usr/bin/env python3
"""Автоматизированный регрессионный прогон мультимодального контура.

Сценарий:
1) Генерирует контрольные изображения и PDF с изображением (для image-derived индексации).
2) Запускает 5 проверок (positive/negative) через API.
3) Печатает отчёт PASS/FAIL и завершает работу с кодом 0/1.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return status, parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        parsed = json.loads(raw) if raw else {"detail": raw or str(exc)}
        return exc.code, parsed
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Запрос {url} превысил timeout={timeout}с") from exc
    except URLError as exc:
        raise RuntimeError(f"Не удалось выполнить запрос {url}: {exc}") from exc


def get_json(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return status, parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        parsed = json.loads(raw) if raw else {"detail": raw or str(exc)}
        return exc.code, parsed
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Запрос {url} превысил timeout={timeout}с") from exc
    except URLError as exc:
        raise RuntimeError(f"Не удалось выполнить запрос {url}: {exc}") from exc


def _python_with_pillow_exists() -> bool:
    probe = [sys.executable, "-c", "from PIL import Image; print('ok')"]
    return subprocess.run(probe, capture_output=True).returncode == 0


def generate_assets(data_dir: Path, marker_token: str, prefer_docker: bool) -> dict[str, str]:
    host_data_dir = data_dir
    container_data_dir = Path("/data")

    vision_dir = host_data_dir / "vision_regression"
    inbox_a_dir = host_data_dir / "inbox" / "csv_ans_docs"
    vision_dir.mkdir(parents=True, exist_ok=True)
    inbox_a_dir.mkdir(parents=True, exist_ok=True)

    def build_generation_code(
        image_http500: Path,
        image_only: Path,
        image_marker: Path,
        marker_pdf: Path,
    ) -> str:
        return f"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

image_http500 = Path({str(image_http500)!r})
image_only = Path({str(image_only)!r})
image_marker = Path({str(image_marker)!r})
marker_pdf = Path({str(marker_pdf)!r})
marker_token = {marker_token!r}


def make_image(path: Path, lines: list[str], *, width: int = 1280, height: int = 720) -> None:
    img = Image.new('RGB', (width, height), color=(248, 250, 252))
    d = ImageDraw.Draw(img)
    title_font = ImageFont.load_default()
    d.rectangle((0, 0, width, 70), fill=(30, 41, 59))
    d.text((20, 25), 'Vision regression fixture', fill=(255, 255, 255), font=title_font)

    y = 120
    for line in lines:
        d.text((40, y), line, fill=(15, 23, 42), font=title_font)
        y += 40

    img.save(path)


make_image(
    image_http500,
    [
        'HTTP 500 Internal Server Error',
        'Request ID: REG-500-TEST',
        'Access denied while calling backend',
    ],
)

make_image(
    image_only,
    [
        'ONLY IMAGE MESSAGE TEST',
        'Expect fallback question + visual evidence',
    ],
)

make_image(
    image_marker,
    [
        f'Unique marker: {{marker_token}}',
        'This image is embedded into PDF for ingestion regression',
    ],
)

img = Image.open(image_marker).convert('RGB')
img.save(marker_pdf, 'PDF', resolution=150.0)
"""

    if not prefer_docker and _python_with_pillow_exists():
        image_http500 = host_data_dir / "vision_regression" / "tc_http500.png"
        image_only = host_data_dir / "vision_regression" / "tc_image_only.png"
        image_marker = host_data_dir / "vision_regression" / "tc_marker.png"
        marker_pdf = host_data_dir / "inbox" / "csv_ans_docs" / "vision_regression_marker.pdf"
        code = build_generation_code(image_http500, image_only, image_marker, marker_pdf)
        subprocess.run([sys.executable, "-c", code], check=True)
    else:
        if host_data_dir != container_data_dir:
            print(
                "Внимание: docker-ветка генерирует ассеты внутри контейнера по пути /data. "
                f"Текущий --data-dir={host_data_dir} на хосте не совпадает с контейнерным путём /data.",
                file=sys.stderr,
            )
        image_http500 = container_data_dir / "vision_regression" / "tc_http500.png"
        image_only = container_data_dir / "vision_regression" / "tc_image_only.png"
        image_marker = container_data_dir / "vision_regression" / "tc_marker.png"
        marker_pdf = container_data_dir / "inbox" / "csv_ans_docs" / "vision_regression_marker.pdf"
        code = build_generation_code(image_http500, image_only, image_marker, marker_pdf)
        cmd = [
            "docker",
            "compose",
            "exec",
            "-T",
            "support-api",
            "python",
            "-c",
            code,
        ]
        subprocess.run(cmd, check=True)

    return {
        "image_http500": "/data/vision_regression/tc_http500.png",
        "image_only": "/data/vision_regression/tc_image_only.png",
        "image_marker": "/data/vision_regression/tc_marker.png",
        "marker_pdf": "/data/inbox/csv_ans_docs/vision_regression_marker.pdf",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Регрессионные проверки OCR/vision/retrieval")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Базовый URL support-api")
    parser.add_argument("--data-dir", default="data", help="Путь к data (смонтирован в контейнер как /data)")
    parser.add_argument("--timeout", type=float, default=90.0, help="Таймаут HTTP-запросов в секундах")
    parser.add_argument(
        "--ingest-timeout",
        type=float,
        default=900.0,
        help="Таймаут шага ingestion (POST /ingest/a/run) в секундах",
    )
    parser.add_argument(
        "--marker-token",
        default="ERR-9A7K-UNIQUE",
        help="Уникальный маркер для проверки retrieval по image-derived chunk",
    )
    parser.add_argument(
        "--prefer-docker-for-assets",
        action="store_true",
        help="Форсировать генерацию изображений внутри контейнера support-api",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    fixtures = generate_assets(data_dir, args.marker_token, prefer_docker=args.prefer_docker_for_assets)

    base = args.api_url.rstrip("/")
    checks: list[CheckResult] = []

    try:
        # TC-01: health
        status, payload = get_json(f"{base}/health", timeout=args.timeout)
        checks.append(
            CheckResult(
                name="TC-01 health endpoint",
                ok=status == 200 and payload.get("status") == "ok",
                details=f"status={status}, body={payload}",
            )
        )
        

        # TC-02: multimodal attachment + OCR text
        multimodal_payload = {
        "model": "local-rag-model",
        "stream": False,
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Что видно на скриншоте?"},
                    {"type": "image_url", "image_url": {"url": f"file://{fixtures['image_http500']}"}},
                ],
            }
        ],
    }
        status, payload = post_json(f"{base}/v1/chat/completions", multimodal_payload, timeout=args.timeout)
        visual = payload.get("visual_evidence") or []
        ocr_text = (visual[0].get("ocr_text") if visual else "") or ""
        tc2_ok = (
            status == 200
            and len(visual) >= 1
            and visual[0].get("image_path") == fixtures["image_http500"]
            and "500" in ocr_text
        )
        checks.append(
            CheckResult(
                name="TC-02 attachment parsing + OCR",
                ok=tc2_ok,
                details=f"status={status}, visual_count={len(visual)}, ocr_excerpt={ocr_text[:120]!r}",
            )
        )

        # TC-03: image-only message fallback question should still be processed
        image_only_payload = {
        "model": "local-rag-model",
        "stream": False,
        "max_tokens": 150,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"file://{fixtures['image_only']}"}},
                ],
            }
        ],
    }
        status, payload = post_json(f"{base}/v1/chat/completions", image_only_payload, timeout=args.timeout)
        visual = payload.get("visual_evidence") or []
        tc3_ok = status == 200 and len(visual) == 1 and visual[0].get("image_path") == fixtures["image_only"]
        checks.append(
            CheckResult(
                name="TC-03 image-only message fallback",
                ok=tc3_ok,
                details=f"status={status}, visual={visual}",
            )
        )

        # TC-04: ingestion + retrieval by marker from image-derived chunk
        ingest_status, ingest_payload = post_json(f"{base}/ingest/a/run", {}, timeout=args.ingest_timeout)
        ask_payload = {
        "question": f"Где встречается маркер {args.marker_token}?",
        "top_k": 8,
        "scope": "all",
        }
        ask_status, ask_resp = post_json(f"{base}/ask", ask_payload, timeout=args.timeout)
        sources = ask_resp.get("sources") or []
        images = ask_resp.get("images") or []
        source_doc_ids = [s.get("doc_id") for s in sources]
        joined_paths = "\n".join(images + [p for s in sources for p in s.get("image_paths", [])])
        tc4_ok = (
            ingest_status == 200
            and ask_status == 200
            and "vision_regression_marker" in source_doc_ids
            and "vision_regression_marker" in joined_paths
        )
        checks.append(
            CheckResult(
                name="TC-04 image-derived retrieval after ingestion",
                ok=tc4_ok,
                details=(
                    f"ingest_status={ingest_status}, ingest={ingest_payload}, ask_status={ask_status}, "
                    f"source_doc_ids={source_doc_ids}, images={images}"
                ),
            )
        )

        # TC-05: invalid image path should not crash and should yield empty OCR + low confidence
        bad_path_payload = {
        "model": "local-rag-model",
        "stream": False,
        "max_tokens": 120,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Что на скриншоте?"},
                    {"type": "image_url", "image_url": {"url": "file:///data/vision_regression/no_such_file.png"}},
                ],
            }
        ],
    }
        status, payload = post_json(f"{base}/v1/chat/completions", bad_path_payload, timeout=args.timeout)
        visual = payload.get("visual_evidence") or []
        confidence = float(visual[0].get("confidence", -1.0)) if visual else -1.0
        tc5_ok = status == 200 and len(visual) >= 1 and not (visual[0].get("ocr_text") or "").strip() and confidence <= 0.2
        checks.append(
            CheckResult(
                name="TC-05 negative: missing image path",
                ok=tc5_ok,
                details=f"status={status}, visual={visual}",
            )
        )
    except RuntimeError as exc:
        print(f"[FAIL] transport/runtime error :: {exc}", file=sys.stderr)
        return 1

    print("\n=== Vision/OCR Regression Report ===")
    failed = 0
    for item in checks:
        mark = "PASS" if item.ok else "FAIL"
        print(f"[{mark}] {item.name} :: {item.details}")
        if not item.ok:
            failed += 1

    print(f"\nTotal: {len(checks)}, Passed: {len(checks) - failed}, Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
