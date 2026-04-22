#!/usr/bin/env python3
"""Диагностика полного RAG-пути: input -> vision -> retrieval -> prompt -> /ask response.

Скрипт запускается на хосте и:
1) отправляет реальный запрос в /ask;
2) запускает внутри контейнера support-api детальную трассировку pipeline;
3) сохраняет объединённый trace JSON (и опционально краткий markdown-отчёт).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
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
    except URLError as exc:
        raise RuntimeError(f"Ошибка HTTP-запроса {url}: {exc}") from exc


IN_CONTAINER_TRACE_CODE = r"""
import base64
import json
from src.api.schemas import AttachmentItem
from src.core.settings import settings
from src.embeddings.client import EmbeddingClient
from src.reranker.client import RerankerClient
from src.rag.prompt_builder import build_prompt
from src.storage.qdrant_repo import QdrantRepo
from src.vision.service import VisionService

payload_raw = base64.b64decode(__import__("os").environ["TRACE_INPUT_B64"]).decode("utf-8")
payload = json.loads(payload_raw)
question = payload["question"]
top_k = int(payload["top_k"])
scope = str(payload["scope"])
image_path = str(payload.get("image_path") or "").strip()

attachments = [AttachmentItem(image_path=image_path)] if image_path else []

vision = VisionService()
visual = [v.model_dump() for v in vision.analyze_attachments(attachments, question)]

qdr = QdrantRepo()
query_vector = EmbeddingClient.embed(question)

collections = []
if scope in ("all", "csv_ans_docs"):
    collections.append("csv_ans_docs")
if scope in ("all", "internal_regulations"):
    collections.append("internal_regulations")

candidate_limit = max(top_k, top_k * settings.retrieval_candidate_pool_multiplier)
raw_by_collection = {}
results = []
for coll in collections:
    rows = qdr.search(coll, query_vector, candidate_limit)
    view = []
    for row in rows:
        p = row.payload or {}
        item = {
            "doc_id": p.get("doc_id", "unknown"),
            "source_type": p.get("source_type", coll),
            "page_number": p.get("page_number"),
            "chunk_id": p.get("chunk_id", str(row.id)),
            "text_preview": (p.get("text", "") or "")[:400],
            "image_paths": p.get("image_paths", []),
            "score": float(row.score),
            "rerank_score": None,
        }
        view.append(item)
        results.append(dict(item))
    raw_by_collection[coll] = view

if settings.retrieval_use_reranker and results:
    rerank_scores = RerankerClient.rerank(question, [item["text_preview"] for item in results])
    for item, score in zip(results, rerank_scores):
        item["rerank_score"] = float(score)
    results.sort(key=lambda x: x["rerank_score"] if x["rerank_score"] is not None else x["score"], reverse=True)
else:
    results.sort(key=lambda x: x["score"], reverse=True)

deduped = []
seen = set()
for item in results:
    key = (item["source_type"], item["doc_id"], item["chunk_id"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(item)

filtered = []
for item in deduped:
    primary = item["rerank_score"] if item["rerank_score"] is not None else item["score"]
    if primary < settings.retrieval_min_score:
        continue
    filtered.append(item)

contexts = filtered[:top_k]
prompt = build_prompt(question, contexts, visual_evidence=visual)

out = {
    "settings_snapshot": {
        "retrieval_use_reranker": settings.retrieval_use_reranker,
        "retrieval_min_score": settings.retrieval_min_score,
        "retrieval_candidate_pool_multiplier": settings.retrieval_candidate_pool_multiplier,
        "vision_runtime_mode": settings.vision_runtime_mode,
    },
    "input": {
        "question": question,
        "top_k": top_k,
        "scope": scope,
        "attachments": [a.model_dump() for a in attachments],
    },
    "visual_evidence": visual,
    "retrieval": {
        "candidate_limit": candidate_limit,
        "raw_by_collection": raw_by_collection,
        "combined_sorted": results[: min(40, len(results))],
        "deduped_count": len(deduped),
        "filtered_count": len(filtered),
        "contexts_used_for_prompt": contexts,
    },
    "final_prompt": prompt,
}
print(json.dumps(out, ensure_ascii=False))
"""


def _run_in_container_trace(input_payload: dict[str, Any]) -> dict[str, Any]:
    encoded = base64.b64encode(json.dumps(input_payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    env = os.environ.copy()
    env["TRACE_INPUT_B64"] = encoded

    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "support-api",
        "python",
        "-c",
        IN_CONTAINER_TRACE_CODE,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            "Не удалось выполнить трассировку внутри контейнера support-api.\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise RuntimeError("Пустой ответ от in-container trace.")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Не удалось распарсить JSON трассировки. Начало вывода:\n{stdout[:1200]}") from exc


def _make_markdown(trace: dict[str, Any]) -> str:
    retrieval = trace.get("retrieval", {})
    contexts = retrieval.get("contexts_used_for_prompt") or []
    lines: list[str] = []
    lines.append("# RAG trace report")
    lines.append("")
    lines.append("## Input")
    lines.append(f"- Question: {trace.get('input', {}).get('question', '')}")
    lines.append(f"- Scope: `{trace.get('input', {}).get('scope', '')}`")
    lines.append(f"- top_k: `{trace.get('input', {}).get('top_k', '')}`")
    lines.append("")
    lines.append("## Settings snapshot")
    settings = trace.get("settings_snapshot", {})
    for k in ("retrieval_use_reranker", "retrieval_min_score", "retrieval_candidate_pool_multiplier", "vision_runtime_mode"):
        lines.append(f"- `{k}`: `{settings.get(k)}`")
    lines.append("")
    lines.append("## Vision evidence")
    for i, item in enumerate(trace.get("visual_evidence") or [], start=1):
        lines.append(
            f"- [{i}] path={item.get('image_path')} confidence={item.get('confidence')} summary={item.get('summary')!r}"
        )
    if not (trace.get("visual_evidence") or []):
        lines.append("- (empty)")
    lines.append("")
    lines.append("## Retrieval summary")
    lines.append(f"- candidate_limit: `{retrieval.get('candidate_limit')}`")
    lines.append(f"- deduped_count: `{retrieval.get('deduped_count')}`")
    lines.append(f"- filtered_count: `{retrieval.get('filtered_count')}`")
    lines.append(f"- contexts_used_for_prompt: `{len(contexts)}`")
    lines.append("")
    lines.append("## Contexts passed to prompt")
    if contexts:
        for i, item in enumerate(contexts, start=1):
            lines.append(
                f"- [{i}] {item.get('source_type')}/{item.get('doc_id')} "
                f"chunk={item.get('chunk_id')} score={item.get('score')} rerank={item.get('rerank_score')}"
            )
    else:
        lines.append("- (empty)")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Трассировка полного RAG-пути: /ask + vision + retrieval + prompt."
    )
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL support-api")
    parser.add_argument("--question", required=True, help="Текст вопроса пользователя")
    parser.add_argument("--image-path", default="", help="Путь к картинке внутри support-api (например /data/runtime_uploads/x.png)")
    parser.add_argument("--top-k", type=int, default=8, help="top_k для retrieval")
    parser.add_argument("--scope", default="all", choices=("all", "csv_ans_docs", "internal_regulations"))
    parser.add_argument("--timeout", type=float, default=120.0, help="Таймаут HTTP запроса /ask")
    parser.add_argument("--out-dir", default="data/rag_traces", help="Каталог для отчётов trace")
    parser.add_argument("--write-markdown", action="store_true", help="Сохранить краткий markdown-отчёт")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ask_payload: dict[str, Any] = {
        "question": args.question,
        "top_k": args.top_k,
        "scope": args.scope,
        "attachments": [],
    }
    if args.image_path.strip():
        ask_payload["attachments"] = [{"image_path": args.image_path.strip()}]

    base = args.api_url.rstrip("/")
    ask_status, ask_response = _post_json(f"{base}/ask", ask_payload, timeout=args.timeout)

    trace_input = {
        "question": args.question,
        "top_k": args.top_k,
        "scope": args.scope,
        "image_path": args.image_path.strip(),
    }
    in_container_trace = _run_in_container_trace(trace_input)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "meta": {
            "timestamp_utc": ts,
            "api_url": base,
        },
        "ask_call": {
            "status": ask_status,
            "request": ask_payload,
            "response": ask_response,
        },
        "pipeline_trace": in_container_trace,
    }

    json_path = out_dir / f"trace_{ts}.json"
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] JSON trace saved: {json_path}")

    if args.write_markdown:
        md_path = out_dir / f"trace_{ts}.md"
        md_path.write_text(_make_markdown(in_container_trace), encoding="utf-8")
        print(f"[OK] Markdown summary saved: {md_path}")

    print("[INFO] ask status:", ask_status)
    print("[INFO] contexts used for prompt:", len(in_container_trace.get("retrieval", {}).get("contexts_used_for_prompt") or []))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
