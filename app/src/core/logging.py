import json
import logging
import os
from datetime import datetime, timezone

from src.core.settings import settings
from src.core.request_context import get_request_id


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
    os.makedirs('/app/logs', exist_ok=True)

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())

    file_handler = logging.FileHandler('/app/logs/support-api.log')
    file_handler.setFormatter(JsonFormatter())

    root.addHandler(stream_handler)
    root.addHandler(file_handler)
