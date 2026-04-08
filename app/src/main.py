import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.ask import router as ask_router
from src.api.ingest_a import router as ingest_a_router
from src.api.ingest_b import router as ingest_b_router
from src.api.schemas import AskRequest
from src.core.logging import configure_logging
from src.rag.orchestrator import RagOrchestrator
from src.telemetry.metrics import HTTP_LATENCY, HTTP_REQUESTS, metrics_response

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title='ЦСВ АНС Support API', version='0.1.0')
app.include_router(ask_router)
app.include_router(ingest_a_router)
app.include_router(ingest_b_router)

orch = RagOrchestrator()


@app.middleware('http')
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start
        path = request.url.path
        method = request.method
        HTTP_REQUESTS.labels(method=method, path=path, status=str(locals().get('status_code', 500))).inc()
        HTTP_LATENCY.labels(method=method, path=path).observe(duration)
        logger.info('request completed', extra={'request_id': request_id})


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.get('/metrics')
def metrics():
    return metrics_response()


@app.post('/v1/chat/completions')
def openai_compat(payload: dict):
    messages = payload.get('messages', [])
    question = ''
    if messages:
        question = messages[-1].get('content', '')

    answer = orch.answer(AskRequest(question=question, top_k=8, scope='all'))
    return {
        'id': f'chatcmpl-{uuid.uuid4().hex[:12]}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': payload.get('model', 'local-rag-model'),
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': answer.answer},
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
