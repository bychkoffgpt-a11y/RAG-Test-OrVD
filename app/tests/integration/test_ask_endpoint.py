"""
Integration tests for the /ask REST endpoint (src/api/ask.py).
"""
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from src.main import app
import src.api.ask as ask_module
from src.api.schemas import AskRequest, AskResponse, SourceItem


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class _FakeSource:
    doc_id: str = 'DOC-1'
    source_type: str = 'csv_ans_docs'
    chunk_id: str = 'DOC-1_ch_0'
    score: float = 0.9
    page_number: int | None = 1
    image_paths: list = field(default_factory=list)
    download_url: str = '/sources/csv_ans_docs/DOC-1/download'

    def model_dump(self):
        return {
            'doc_id': self.doc_id,
            'source_type': self.source_type,
            'chunk_id': self.chunk_id,
            'score': self.score,
            'page_number': self.page_number,
            'image_paths': self.image_paths,
            'download_url': self.download_url,
        }


@dataclass
class _FakeAskResponse:
    answer: str = 'Тестовый ответ'
    sources: list = field(default_factory=lambda: [_FakeSource()])
    images: list = field(default_factory=list)
    visual_evidence: list = field(default_factory=list)


class _FakeOrch:
    def __init__(self, response: _FakeAskResponse | None = None, side_effect=None):
        self.last_payload: AskRequest | None = None
        self.last_kwargs: dict = {}
        self._response = response or _FakeAskResponse()
        self._side_effect = side_effect

    def answer(self, payload: AskRequest, **kwargs):
        self.last_payload = payload
        self.last_kwargs = kwargs
        if self._side_effect is not None:
            raise self._side_effect
        return self._response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ask_client(monkeypatch):
    dummy = _FakeOrch()
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)
    return client, dummy


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_ask_returns_200_and_answer(ask_client):
    client, dummy = ask_client

    resp = client.post('/ask', json={'question': 'Что такое ЦСВ?', 'top_k': 5, 'scope': 'all'})

    assert resp.status_code == 200
    data = resp.json()
    assert data['answer'] == 'Тестовый ответ'
    assert isinstance(data['sources'], list)


def test_ask_passes_question_to_orchestrator(ask_client):
    client, dummy = ask_client

    client.post('/ask', json={'question': 'Как подать заявку?', 'top_k': 8, 'scope': 'all'})

    assert dummy.last_payload is not None
    assert dummy.last_payload.question == 'Как подать заявку?'
    assert dummy.last_payload.top_k == 8
    assert dummy.last_payload.scope == 'all'


def test_ask_passes_endpoint_kwarg_to_orchestrator(ask_client):
    client, dummy = ask_client

    client.post('/ask', json={'question': 'Тест эндпоинта'})

    assert dummy.last_kwargs.get('endpoint') == '/ask'


def test_ask_returns_sources_list(ask_client):
    client, dummy = ask_client

    resp = client.post('/ask', json={'question': 'Откуда данные?'})

    assert resp.status_code == 200
    sources = resp.json()['sources']
    assert len(sources) == 1
    assert sources[0]['doc_id'] == 'DOC-1'


# ---------------------------------------------------------------------------
# Validation errors (min_length=3 on question field)
# ---------------------------------------------------------------------------

def test_ask_rejects_question_shorter_than_3_chars(ask_client):
    client, _ = ask_client

    resp = client.post('/ask', json={'question': 'Ок'})

    assert resp.status_code == 422


def test_ask_rejects_missing_question(ask_client):
    client, _ = ask_client

    resp = client.post('/ask', json={'top_k': 5})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error handling → HTTP status codes
# ---------------------------------------------------------------------------

def test_ask_returns_504_on_llm_timeout(monkeypatch):
    dummy = _FakeOrch(side_effect=httpx.TimeoutException('timeout'))
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)

    resp = client.post('/ask', json={'question': 'Таймаут вопрос?'})

    assert resp.status_code == 504
    assert 'Таймаут' in resp.json()['detail']


def test_ask_returns_502_on_llm_http_error(monkeypatch):
    dummy = _FakeOrch(side_effect=httpx.HTTPError('connection refused'))
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)

    resp = client.post('/ask', json={'question': 'HTTP ошибка?'})

    assert resp.status_code == 502
    assert 'LLM backend' in resp.json()['detail']


def test_ask_returns_500_on_unexpected_error(monkeypatch):
    dummy = _FakeOrch(side_effect=RuntimeError('unexpected crash'))
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)

    resp = client.post('/ask', json={'question': 'Неожиданная ошибка?'})

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TypeError backwards-compat fallback in ask.py
# ---------------------------------------------------------------------------

def test_ask_falls_back_when_orchestrator_raises_type_error_on_kwargs(monkeypatch):
    """
    ask.py wraps orch.answer(..., endpoint=..., pre_processing_sec=...) in
    try/except TypeError and retries without those kwargs.
    """
    class _OldStyleOrch:
        def __init__(self):
            self.called_without_kwargs = False

        def answer(self, payload, **kwargs):
            if kwargs:
                raise TypeError('unexpected keyword argument')
            self.called_without_kwargs = True
            return _FakeAskResponse()

    dummy = _OldStyleOrch()
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)

    resp = client.post('/ask', json={'question': 'Совместимость'})

    assert resp.status_code == 200
    assert dummy.called_without_kwargs
