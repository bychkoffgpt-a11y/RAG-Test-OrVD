import threading

from src.core.request_context import get_request_id, reset_request_id, set_request_id


def test_get_request_id_returns_none_by_default():
    # Each test runs in a fresh context var state unless set
    assert get_request_id() is None


def test_set_and_get_request_id():
    token = set_request_id('req-abc-123')
    try:
        assert get_request_id() == 'req-abc-123'
    finally:
        reset_request_id(token)


def test_reset_request_id_restores_previous_value():
    outer_token = set_request_id('outer-id')
    inner_token = set_request_id('inner-id')

    assert get_request_id() == 'inner-id'

    reset_request_id(inner_token)
    assert get_request_id() == 'outer-id'

    reset_request_id(outer_token)
    assert get_request_id() is None


def test_request_id_is_isolated_between_threads():
    """ContextVar values are per-thread; threads start with default (None)."""
    results: dict[str, str | None] = {}

    def worker(name: str, request_id: str) -> None:
        token = set_request_id(request_id)
        results[name] = get_request_id()
        reset_request_id(token)

    t1 = threading.Thread(target=worker, args=('t1', 'id-thread-1'))
    t2 = threading.Thread(target=worker, args=('t2', 'id-thread-2'))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results['t1'] == 'id-thread-1'
    assert results['t2'] == 'id-thread-2'


def test_set_request_id_returns_token_for_reset():
    token = set_request_id('temp-id')
    assert token is not None
    reset_request_id(token)
    assert get_request_id() is None
