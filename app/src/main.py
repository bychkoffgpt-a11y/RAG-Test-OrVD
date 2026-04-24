import logging
import json
import time
import uuid
import base64
import binascii
import mimetypes
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from src.api.ask import router as ask_router
from src.api.ingest_a import router as ingest_a_router
from src.api.ingest_b import router as ingest_b_router
from src.api.sources import router as sources_router
from src.api.schemas import AskRequest, AttachmentItem
from src.core.logging import configure_logging
from src.core.request_context import reset_request_id, set_request_id
from src.core.settings import settings
from src.rag.answer_formatter import append_grounding_markdown, append_sources_markdown
from src.rag.orchestrator import RagOrchestrator
from src.telemetry.metrics import HTTP_LATENCY, HTTP_REQUESTS, metrics_response
from src.vision.service import VisionService

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title='ЦСВ АНС Support API', version='0.1.0')
app.include_router(ask_router)
app.include_router(ingest_a_router)
app.include_router(ingest_b_router)
app.include_router(sources_router)

orch = RagOrchestrator()


@app.on_event('startup')
def preload_vision_runtime_models() -> None:
    VisionService.preload_runtime_models()


def _resolve_path_alias(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        return normalized

    mappings = [
        item.strip()
        for item in settings.vision_attachment_path_aliases.split(';')
        if item.strip()
    ]
    for mapping in mappings:
        if '=' not in mapping:
            continue
        source_prefix, target_prefix = mapping.split('=', 1)
        source_prefix = source_prefix.strip()
        target_prefix = target_prefix.strip()
        if source_prefix and target_prefix and normalized.startswith(source_prefix):
            return normalized.replace(source_prefix, target_prefix, 1)
    return normalized


def _ensure_runtime_upload_dir() -> Path:
    target = Path(settings.file_storage_root).joinpath('runtime_uploads')
    target.mkdir(parents=True, exist_ok=True)
    return target


def _materialize_data_url(raw_url: str) -> str | None:
    if not raw_url.startswith('data:image/'):
        return None
    if ';base64,' not in raw_url:
        logger.warning('attachment_data_url_unsupported_encoding')
        return None

    header, payload = raw_url.split(';base64,', 1)
    mime = header[len('data:') :].strip().lower()
    if mime not in settings.vision_attachment_allowed_mime_types:
        logger.warning('attachment_data_url_unsupported_mime', extra={'mime': mime})
        return None

    try:
        decoded = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        logger.warning('attachment_data_url_decode_failed')
        return None

    if len(decoded) > settings.vision_attachment_max_bytes:
        logger.warning(
            'attachment_data_url_too_large',
            extra={'bytes': len(decoded), 'max_bytes': settings.vision_attachment_max_bytes},
        )
        return None

    suffix = mimetypes.guess_extension(mime) or '.png'
    file_path = _ensure_runtime_upload_dir().joinpath(f'{uuid.uuid4().hex}{suffix}')
    file_path.write_bytes(decoded)
    return str(file_path)


def _materialize_remote_url(raw_url: str) -> str | None:
    if not raw_url.startswith(('http://', 'https://')):
        return None

    timeout = httpx.Timeout(10.0, connect=5.0)
    try:
        response = httpx.get(raw_url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError:
        logger.warning('attachment_remote_fetch_failed', extra={'url': raw_url})
        return None

    if response.status_code >= 400:
        logger.warning('attachment_remote_bad_status', extra={'url': raw_url, 'status_code': response.status_code})
        return None

    payload = response.content
    if len(payload) > settings.vision_attachment_max_bytes:
        logger.warning(
            'attachment_remote_too_large',
            extra={'url': raw_url, 'bytes': len(payload), 'max_bytes': settings.vision_attachment_max_bytes},
        )
        return None

    content_type = str(response.headers.get('content-type', '')).split(';', 1)[0].strip().lower()
    if content_type and content_type not in settings.vision_attachment_allowed_mime_types:
        logger.warning('attachment_remote_unsupported_mime', extra={'url': raw_url, 'mime': content_type})
        return None

    guessed_suffix = Path(raw_url).suffix
    if guessed_suffix:
        suffix = guessed_suffix
    else:
        suffix = mimetypes.guess_extension(content_type) if content_type else '.png'
        suffix = suffix or '.png'

    file_path = _ensure_runtime_upload_dir().joinpath(f'{uuid.uuid4().hex}{suffix}')
    file_path.write_bytes(payload)
    return str(file_path)


def _normalize_attachment_path(raw_url: str) -> str | None:
    normalized = raw_url.strip()
    if not normalized:
        return None
    if normalized.startswith('file://'):
        normalized = normalized[len('file://') :]

    materialized = _materialize_data_url(normalized)
    if materialized:
        return materialized

    materialized = _materialize_remote_url(normalized)
    if materialized:
        return materialized

    return _resolve_path_alias(normalized)


def _extract_attachments_from_message_content(content) -> list[AttachmentItem]:
    attachments: list[AttachmentItem] = []
    if not isinstance(content, list):
        return attachments

    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get('type') not in {'image_url', 'input_image', 'image'}:
            continue

        raw_url = None
        image_url = part.get('image_url')
        if isinstance(image_url, dict):
            raw_url = image_url.get('url')
        elif isinstance(image_url, str):
            raw_url = image_url
        if raw_url is None:
            raw_url = part.get('url')

        if not isinstance(raw_url, str) or not raw_url.strip():
            continue

        normalized = _normalize_attachment_path(raw_url)
        if not normalized:
            continue
        attachments.append(AttachmentItem(image_path=normalized))

    return attachments


@app.middleware('http')
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers['X-Request-ID'] = request_id
        return response
    finally:
        duration = time.perf_counter() - start
        path = request.url.path
        method = request.method
        HTTP_REQUESTS.labels(method=method, path=path, status=str(locals().get('status_code', 500))).inc()
        HTTP_LATENCY.labels(method=method, path=path).observe(duration)
        if not (settings.suppress_metrics_request_logs and path == '/metrics'):
            logger.info('request completed', extra={'request_id': request_id})
        reset_request_id(token)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.get('/metrics')
def metrics():
    return metrics_response()


@app.post('/v1/chat/completions')
def openai_compat(payload: dict, request: Request):
    started = time.perf_counter()
    logger.info(
        'openai_compat_request_received',
        extra={
            'stream': payload.get('stream') is True,
            'has_messages': isinstance(payload.get('messages'), list),
            'messages_count': len(payload.get('messages', [])) if isinstance(payload.get('messages'), list) else 0,
        },
    )
    messages = payload.get('messages', [])
    question = ''
    attachments: list[AttachmentItem] = []
    for message in reversed(messages):
        if message.get('role') != 'user':
            continue

        content = message.get('content', '')
        extracted_attachments: list[AttachmentItem] = []
        if isinstance(content, str):
            question = content.strip()
        elif isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'text':
                    text_parts.append(part.get('text', ''))
            question = '\n'.join([p for p in text_parts if p]).strip()
            extracted_attachments = _extract_attachments_from_message_content(content)

        if extracted_attachments and not attachments:
            attachments = extracted_attachments

        if question:
            if extracted_attachments:
                attachments = extracted_attachments
            break

    if not question.strip():
        if attachments:
            question = 'Опишите, что видно на скриншоте, и предложите решение проблемы.'
            logger.info('openai_compat_question_fallback_used')
        else:
            logger.warning('openai_compat_question_missing')
            return JSONResponse(status_code=400, content={'detail': 'Не удалось извлечь текст вопроса из messages.'})

    raw_max_tokens = payload.get('max_tokens')
    if raw_max_tokens is None:
        max_tokens = 1024
    else:
        max_tokens = int(raw_max_tokens)

    raw_temperature = payload.get('temperature')
    if raw_temperature is None:
        temperature = 0.1
    else:
        temperature = float(raw_temperature)

    try:
        ask_payload = AskRequest(question=question, top_k=8, scope='all', attachments=attachments)
        try:
            answer = orch.answer(
                ask_payload,
                max_tokens=max_tokens,
                temperature=temperature,
                endpoint='/v1/chat/completions',
                pre_processing_sec=time.perf_counter() - started,
            )
        except TypeError:
            answer = orch.answer(ask_payload, max_tokens=max_tokens, temperature=temperature)
    except ValidationError as exc:
        return JSONResponse(status_code=400, content={'detail': str(exc)})
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={'detail': 'Таймаут запроса к LLM. Попробуйте сократить вопрос.'})
    except httpx.HTTPError as exc:
        return JSONResponse(status_code=502, content={'detail': f'Ошибка LLM backend: {exc}'})

    logger.info('openai_compat_generation_params', extra={'max_tokens': max_tokens, 'temperature': temperature})

    completion_id = f'chatcmpl-{uuid.uuid4().hex[:12]}'
    created = int(time.time())
    model = payload.get('model', 'local-rag-model')
    is_stream = payload.get('stream') is True

    rendered_answer = append_grounding_markdown(answer.answer, answer.sources, base_url=str(request.base_url))
    rendered_answer = append_sources_markdown(rendered_answer, answer.sources, base_url=str(request.base_url))
    logger.info(
        'openai_compat_answer_ready',
        extra={
            'stream': is_stream,
            'completion_id': completion_id,
            'answer_chars': len(rendered_answer),
            'sources_count': len(answer.sources),
            'images_count': len(answer.images),
            'visual_evidence_count': len(answer.visual_evidence),
        },
    )

    if is_stream:
        def event_stream():
            logger.info('openai_compat_stream_started', extra={'completion_id': completion_id})
            first_chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': model,
                'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}],
            }
            yield f'data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n'

            content_chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': model,
                'choices': [{'index': 0, 'delta': {'content': rendered_answer}, 'finish_reason': None}],
            }
            yield f'data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n'

            final_chunk = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created,
                'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
            }
            yield f'data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n'
            yield 'data: [DONE]\n\n'
            logger.info('openai_compat_stream_finished', extra={'completion_id': completion_id})

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    logger.info('openai_compat_non_stream_response_sent', extra={'completion_id': completion_id})
    return {
        'id': completion_id,
        'object': 'chat.completion',
        'created': created,
        'model': model,
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': rendered_answer},
                'finish_reason': 'stop',
            }
        ],
        'sources': [s.model_dump() for s in answer.sources],
        'images': answer.images,
        'visual_evidence': [item.model_dump() for item in answer.visual_evidence],
    }


@app.get('/v1/models')
def openai_models():
    return {
        'object': 'list',
        'data': [
            {
                'id': 'local-rag-model',
                'object': 'model',
                'created': 0,
                'owned_by': 'local',
            }
        ],
    }


@app.exception_handler(Exception)
async def exception_handler(_: Request, exc: Exception):
    logger.exception('Unhandled error: %s', exc)
    return JSONResponse(status_code=500, content={'detail': 'Внутренняя ошибка сервера'})
