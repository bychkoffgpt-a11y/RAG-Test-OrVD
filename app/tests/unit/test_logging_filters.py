import logging

from src.core.logging import SuppressMetricsAccessFilter


def test_suppress_metrics_access_filter_drops_metrics_tuple_args():
    filt = SuppressMetricsAccessFilter()
    record = logging.LogRecord(
        name='uvicorn.access',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=('127.0.0.1:12345', 'GET', '/metrics', '1.1', 200),
        exc_info=None,
    )

    assert filt.filter(record) is False


def test_suppress_metrics_access_filter_keeps_non_metrics_paths():
    filt = SuppressMetricsAccessFilter()
    record = logging.LogRecord(
        name='uvicorn.access',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=('127.0.0.1:12345', 'GET', '/health', '1.1', 200),
        exc_info=None,
    )

    assert filt.filter(record) is True
