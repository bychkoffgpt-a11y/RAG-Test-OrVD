"""
Additional edge-case tests for LlmClient that complement test_llm_client.py.
"""
import httpx
import pytest

from src.llm.client import LlmClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError('error', request=None, response=None)


# ---------------------------------------------------------------------------
# Both endpoints fail
# ---------------------------------------------------------------------------

def test_generate_raises_when_completion_endpoint_also_fails(monkeypatch):
    """If chat/completions returns 404 AND /completion raises, the error propagates."""

    def _fake_post(url, json, timeout):
        if url.endswith('/v1/chat/completions'):
            return _Resp(404, {})
        raise httpx.ConnectError('refused')

    monkeypatch.setattr(httpx, 'post', _fake_post)

    with pytest.raises(httpx.ConnectError):
        LlmClient().generate('Вопрос?')


def test_generate_raises_when_completion_returns_error_status(monkeypatch):
    def _fake_post(url, json, timeout):
        if url.endswith('/v1/chat/completions'):
            return _Resp(404, {})
        return _Resp(500, {'error': 'internal'})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        LlmClient().generate('Вопрос?')


# ---------------------------------------------------------------------------
# _looks_russian
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected', [
    ('Это нормальный русский текст для проверки', True),
    ('Based on information please check the document', False),
    # Predominantly Cyrillic text with a few ASCII abbreviations
    ('Документ содержит поля API и JSON формата', True),
    # More Latin chars than Cyrillic → returns False
    ('Смешанный mixed текст with some latin letters здесь', False),
    ('12345 678 90 --- *** !!!', False),  # no letters at all
    ('Кр', False),  # too few Cyrillic chars (<8)
    ('', False),
])
def test_looks_russian_detects_language_correctly(text, expected):
    assert LlmClient._looks_russian(text) is expected


# ---------------------------------------------------------------------------
# _looks_truncated
# ---------------------------------------------------------------------------

# Must be >= 80 chars so _looks_truncated doesn't return False due to length check
_LONG_PREFIX = 'Это очень длинный текст, длиннее восьмидесяти символов, который нужен для проверки логики. '


@pytest.mark.parametrize('suffix,expected', [
    ('.', False),    # ends with period → complete sentence
    ('?', False),    # ends with question mark
    ('!', False),    # ends with exclamation
    (':', False),    # ends with colon
    (';', False),    # ends with semicolon
    ('»', False),    # ends with closing quote
    (')', False),    # ends with closing paren
    # NOTE: '...' (ASCII) is caught by the endswith('.') check first → False
    ('...', False),
    ('…', True),     # Unicode ellipsis U+2026 → truncated
    ('обрыв', True), # ends with alphanumeric (mid-word truncation)
])
def test_looks_truncated_detects_truncation_correctly(suffix, expected):
    text = _LONG_PREFIX + suffix
    assert LlmClient._looks_truncated(text) is expected


def test_looks_truncated_returns_false_for_short_text():
    assert LlmClient._looks_truncated('Слишком короткий') is False


def test_looks_truncated_returns_true_for_numbered_list_mid_item():
    text = (
        'Инструкция по устранению неполадок:\n'
        '1. Проверьте соединение с сетью и перезагрузите роутер.\n'
        '2. Очистите кэш браузера и попробуйте снова.\n'
        '3. Если проблема не устранена Э'
    )
    assert LlmClient._looks_truncated(text) is True


# ---------------------------------------------------------------------------
# _merge_continuation
# ---------------------------------------------------------------------------

def test_merge_continuation_joins_with_space():
    merged = LlmClient._merge_continuation('Ответ был', 'продолжен здесь.')
    assert merged == 'Ответ был продолжен здесь.'


def test_merge_continuation_returns_continuation_when_it_already_contains_answer():
    answer = 'Ответ обрывается'
    continuation = 'Ответ обрывается на полуслове. Полная версия.'
    merged = LlmClient._merge_continuation(answer, continuation)
    assert merged == continuation


def test_merge_continuation_strips_extra_whitespace():
    merged = LlmClient._merge_continuation('Первая часть   ', '   вторая часть.')
    assert merged == 'Первая часть вторая часть.'


# ---------------------------------------------------------------------------
# _enforce_russian — rewrite fails gracefully
# ---------------------------------------------------------------------------

def test_enforce_russian_returns_original_when_rewrite_fails(monkeypatch):
    """If the rewrite HTTP call raises, original answer is returned unchanged."""
    calls = []

    def _fake_post(url, json, timeout):
        calls.append(url)
        if len(calls) == 1:
            return _Resp(200, {'choices': [{'message': {'content': 'English only answer here for testing'}}]})
        raise httpx.ConnectError('rewrite endpoint down')

    monkeypatch.setattr(httpx, 'post', _fake_post)

    answer = LlmClient().generate('Question?')
    assert answer == 'English only answer here for testing'


def test_enforce_russian_skips_rewrite_for_already_russian_text(monkeypatch):
    calls = []

    def _fake_post(url, json, timeout):
        calls.append(url)
        return _Resp(200, {'choices': [{'message': {'content': 'Нормальный русский ответ без латинских букв и символов'}}]})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    answer = LlmClient().generate('Что такое ЦСВ?')

    assert answer == 'Нормальный русский ответ без латинских букв и символов'
    assert len(calls) == 1  # no rewrite call


# ---------------------------------------------------------------------------
# trace dict is populated correctly
# ---------------------------------------------------------------------------

def test_generate_populates_trace_with_transport_and_answer(monkeypatch):
    def _fake_post(url, json, timeout):
        return _Resp(200, {'choices': [{'message': {'content': 'Ответ готов'}}]})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    trace: dict = {}
    LlmClient().generate('Вопрос', trace=trace)

    assert trace['transport'] == 'chat_completions'
    assert trace['answer'] == 'Ответ готов'
    assert 'chat_status_code' in trace
    assert trace['chat_status_code'] == 200


def test_generate_populates_trace_with_completion_transport(monkeypatch):
    def _fake_post(url, json, timeout):
        if url.endswith('/v1/chat/completions'):
            return _Resp(404, {})
        return _Resp(200, {'content': 'Фолбэк ответ'})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    trace: dict = {}
    LlmClient().generate('Вопрос', trace=trace)

    assert trace['transport'] == 'completion'
    assert 'completion_status_code' in trace
