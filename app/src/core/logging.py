import json
import logging
import os
from datetime import datetime, timezone

from src.core.settings import settings
from src.core.request_context import get_request_id


class SuppressMetricsAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and args[2] == '/metrics':
            return False
        return '"/metrics ' not in record.getMessage()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if hasattr(record, 'request_id'):
            payload['request_id'] = record.request_id
        elif get_request_id() is not None:
            payload['request_id'] = get_request_id()
        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    log_dir = os.environ.get('LOG_DIR', '/app/logs')
    fallback_log_dir = os.path.join(os.getcwd(), 'logs')

    try:
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, 'support-api.log')
    except PermissionError:
        os.makedirs(fallback_log_dir, exist_ok=True)
        file_path = os.path.join(fallback_log_dir, 'support-api.log')

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())

    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(JsonFormatter())

    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    if settings.suppress_metrics_access_logs:
        uvicorn_access_logger = logging.getLogger('uvicorn.access')
        metrics_filter = SuppressMetricsAccessFilter()
        uvicorn_access_logger.addFilter(metrics_filter)
        for handler in uvicorn_access_logger.handlers:
            handler.addFilter(metrics_filter)
