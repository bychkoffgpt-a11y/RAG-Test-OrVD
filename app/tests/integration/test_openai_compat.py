from dataclasses import dataclass

from fastapi.testclient import TestClient

from src.main import app
import src.main as main_module


@dataclass
class DummySource:
    doc_id: str = 'doc-1'
    source_type: str = 'csv_ans_docs'
    download_url: str = '/sources/csv_ans_docs/doc-1/download'

    def model_dump(self):
        return {'doc_id': self.doc_id}


@dataclass
class DummyAnswer:
    answer: str = 'Тестовый ответ'
    sources: list = None
    images: list = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = [DummySource()]
        if self.images is None:
            self.images = []


class DummyOrchestrator:
    def answer(self, ask_payload, max_tokens: int, temperature: float):
        return DummyAnswer()


def test_chat_completions_non_stream_returns_200(monkeypatch):
    monkeypatch.setattr(main_module, 'orch', DummyOrchestrator())
    client = TestClient(app)

    payload = {
        'model': 'local-rag-model',
        'messages': [{'role': 'user', 'content': 'Привет'}],
        'stream': False,
    }

    response = client.post('/v1/chat/completions', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['object'] == 'chat.completion'
    assert 'Тестовый ответ' in data['choices'][0]['message']['content']
    assert 'Источники для скачивания' in data['choices'][0]['message']['content']
    assert '/sources/csv_ans_docs/doc-1/download' in data['choices'][0]['message']['content']


def test_chat_completions_stream_returns_sse_chunks(monkeypatch):
    monkeypatch.setattr(main_module, 'orch', DummyOrchestrator())
    client = TestClient(app)

    payload = {
        'model': 'local-rag-model',
        'messages': [{'role': 'user', 'content': 'Привет'}],
        'stream': True,
    }

    with client.stream('POST', '/v1/chat/completions', json=payload) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        body = ''.join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert '"object": "chat.completion.chunk"' in body
    assert '"finish_reason": "stop"' in body
    assert 'data: [DONE]' in body


def test_chat_completions_uses_last_user_message(monkeypatch):
    monkeypatch.setattr(main_module, 'orch', DummyOrchestrator())
    client = TestClient(app)

    payload = {
        'model': 'local-rag-model',
        'messages': [
            {'role': 'user', 'content': 'Первый вопрос'},
            {'role': 'assistant', 'content': 'Ответ модели'},
            {'role': 'assistant', 'content': ''},
        ],
        'stream': False,
    }

    response = client.post('/v1/chat/completions', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert 'Тестовый ответ' in data['choices'][0]['message']['content']


def test_chat_completions_accepts_null_generation_params(monkeypatch):
    monkeypatch.setattr(main_module, 'orch', DummyOrchestrator())
    client = TestClient(app)

    payload = {
        'model': 'local-rag-model',
        'messages': [{'role': 'user', 'content': 'Привет'}],
        'max_tokens': None,
        'temperature': None,
        'stream': False,
    }

    response = client.post('/v1/chat/completions', json=payload)

    assert response.status_code == 200
