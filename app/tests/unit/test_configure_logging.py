import logging

from src.core.logging import configure_logging


def test_configure_logging_filehandler_permission_error_does_not_raise(monkeypatch):
    real_stream_handler = logging.StreamHandler

    def fake_file_handler(*args, **kwargs):
        raise PermissionError('denied')

    monkeypatch.setattr(logging, 'FileHandler', fake_file_handler)
    monkeypatch.setattr(logging, 'StreamHandler', lambda *args, **kwargs: real_stream_handler())

    configure_logging()

    root = logging.getLogger()
    assert any(isinstance(handler, real_stream_handler) for handler in root.handlers)
