"""
Shared test fixtures and fakes used across multiple test modules.
"""
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Shared fake data classes
# ---------------------------------------------------------------------------

@dataclass
class FakeSource:
    doc_id: str = 'doc-1'
    source_type: str = 'csv_ans_docs'
    chunk_id: str = 'chunk-1'
    score: float = 0.9
    page_number: int | None = 1
    image_paths: list = field(default_factory=list)
    download_url: str = '/sources/csv_ans_docs/doc-1/download'

    def model_dump(self) -> dict:
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
class FakeVisualEvidence:
    image_path: str = '/tmp/screen.png'
    ocr_text: str = 'HTTP 500'
    summary: str = 'Ошибка на экране'
    confidence: float = 0.8
    task_type: str = 'text'
    vlm_output_format: str | None = None
    vlm_json_parse_ok: bool | None = None
    vlm_raw_length: int | None = None
    vlm_fallback_applied: bool | None = None
    vlm_max_new_tokens_used: int | None = None

    def model_dump(self) -> dict:
        return {
            'image_path': self.image_path,
            'ocr_text': self.ocr_text,
            'summary': self.summary,
            'confidence': self.confidence,
            'task_type': self.task_type,
            'vlm_output_format': self.vlm_output_format,
            'vlm_json_parse_ok': self.vlm_json_parse_ok,
            'vlm_raw_length': self.vlm_raw_length,
            'vlm_fallback_applied': self.vlm_fallback_applied,
            'vlm_max_new_tokens_used': self.vlm_max_new_tokens_used,
        }


@dataclass
class FakeAskResponse:
    answer: str = 'Тестовый ответ'
    sources: list = field(default_factory=lambda: [FakeSource()])
    images: list = field(default_factory=list)
    visual_evidence: list = field(default_factory=lambda: [FakeVisualEvidence()])


# ---------------------------------------------------------------------------
# Fake orchestrator used by integration tests
# ---------------------------------------------------------------------------

class FakeOrchestrator:
    """Drop-in replacement for RagOrchestrator in integration tests."""

    def __init__(
        self,
        answer_text: str = 'Тестовый ответ',
        sources: list | None = None,
        images: list | None = None,
        visual_evidence: list | None = None,
    ) -> None:
        self.last_payload: Any = None
        self.last_max_tokens: int | None = None
        self.last_temperature: float | None = None
        self._response = FakeAskResponse(
            answer=answer_text,
            sources=sources if sources is not None else [FakeSource()],
            images=images if images is not None else [],
            visual_evidence=visual_evidence if visual_evidence is not None else [FakeVisualEvidence()],
        )
        self.vision = FakeVision()

    def answer(self, ask_payload, max_tokens: int = 1024, temperature: float = 0.1, **kwargs):
        self.last_payload = ask_payload
        self.last_max_tokens = max_tokens
        self.last_temperature = temperature
        return self._response

    def _render_visual_answer(self, visual_evidence, max_tokens: int = 1024, temperature: float = 0.1):
        self.last_max_tokens = max_tokens
        self.last_temperature = temperature
        return f'visual:{len(visual_evidence)}'

    def _build_visual_answer_fallback(self, visual_evidence) -> str:
        parts = [
            str(item.get('ocr_text') or '').strip()
            for item in (visual_evidence or [])
            if isinstance(item, dict)
        ]
        return '\n'.join(p for p in parts if p).strip()


class FakeVision:
    def analyze_attachments(self, attachments, question, **kwargs):
        return [FakeVisualEvidence().model_dump()]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_orch() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture()
def http_client(monkeypatch, fake_orch):
    """TestClient with the orchestrator replaced by FakeOrchestrator."""
    from fastapi.testclient import TestClient
    from src.main import app
    import src.main as main_module

    monkeypatch.setattr(main_module, 'orch', fake_orch)
    return TestClient(app), fake_orch


@pytest.fixture()
def mock_connect(monkeypatch):
    """Yields a (conn_mock, cursor_mock) pair with psycopg.connect mocked."""
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor

    monkeypatch.setattr('src.storage.postgres_repo.connect', lambda dsn: conn)
    return conn, cursor
