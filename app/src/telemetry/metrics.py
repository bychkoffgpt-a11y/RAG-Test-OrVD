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


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
