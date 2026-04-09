import logging
import json
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from src.api.ask import router as ask_router
from src.api.ingest_a import router as ingest_a_router
from src.api.ingest_b import router as ingest_b_router
from src.api.sources import router as sources_router
from src.api.schemas import AskRequest
from src.core.logging import configure_logging
from src.core.request_context import reset_request_id, set_request_id
from src.rag.answer_formatter import append_sources_markdown
from src.rag.orchestrator import RagOrchestrator
from src.telemetry.metrics import HTTP_LATENCY, HTTP_REQUESTS, metrics_response

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title='ЦСВ АНС Support API', version='0.1.0')
app.include_router(ask_router)
app.include_router(ingest_a_router)
app.include_router(ingest_b_router)
app.include_router(sources_router)

orch = RagOrchestrator()


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
    messages = payload.get('messages', [])
    question = ''
    for message in reversed(messages):
        if message.get('role') != 'user':
            continue

        content = message.get('content', '')
        if isinstance(content, str):
            question = content.strip()
        elif isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'text':
                    text_parts.append(part.get('text', ''))
            question = '\n'.join([p for p in text_parts if p]).strip()

        if question:
            break

    if not question.strip():
        return JSONResponse(status_code=400, content={'detail': 'Не удалось извлечь текст вопроса из messages.'})

    raw_max_tokens = payload.get('max_tokens')
    if raw_max_tokens is None:
        max_tokens = 512
    else:
        max_tokens = int(raw_max_tokens)

    raw_temperature = payload.get('temperature')
    if raw_temperature is None:
        temperature = 0.1
    else:
        temperature = float(raw_temperature)

    try:
        ask_payload = AskRequest(question=question, top_k=8, scope='all')
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

    rendered_answer = append_sources_markdown(answer.answer, answer.sources, base_url=str(request.base_url))

    if is_stream:
        def event_stream():
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

        return StreamingResponse(event_stream(), media_type='text/event-stream')

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
