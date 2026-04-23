from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    'http_requests_total',
    'Всего HTTP запросов',
    ['method', 'path', 'status']
)

HTTP_LATENCY = Histogram(
    'http_request_duration_seconds',
    'Длительность HTTP запросов',
    ['method', 'path']
)

RAG_STAGE_LATENCY = Histogram(
    'rag_stage_duration_seconds',
    'Длительность отдельных этапов RAG-пайплайна',
    ['endpoint', 'stage', 'has_attachments', 'scope', 'vision_mode'],
)


def observe_rag_stage_latency(
    *,
    endpoint: str,
    stage: str,
    has_attachments: bool,
    scope: str,
    vision_mode: str,
    duration_sec: float,
) -> None:
    RAG_STAGE_LATENCY.labels(
        endpoint=endpoint,
        stage=stage,
        has_attachments='1' if has_attachments else '0',
        scope=scope,
        vision_mode=vision_mode,
    ).observe(max(duration_sec, 0.0))


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
