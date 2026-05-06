"""
Tests for helper functions in main.py and minor endpoints that are not
covered by test_openai_compat.py: /health, /metrics, /v1/models,
X-Request-ID propagation, error paths in image materialization,
and the _dedupe_chart_sections / _apply_visual_answer_fallback utilities.
"""
import base64
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import (
    app,
    _dedupe_chart_sections,
    _apply_visual_answer_fallback,
    _materialize_data_url,
    _materialize_remote_url,
    _resolve_path_alias,
    _looks_like_chart_case,
)
import src.main as main_module


# ---------------------------------------------------------------------------
# Minor endpoints
# ---------------------------------------------------------------------------

def test_health_endpoint_returns_ok():
    client = TestClient(app)
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.json() == {'status': 'ok'}


def test_metrics_endpoint_returns_prometheus_content():
    client = TestClient(app)
    resp = client.get('/metrics')
    assert resp.status_code == 200
    assert 'http_requests_total' in resp.text


def test_v1_models_returns_local_model():
    client = TestClient(app)
    resp = client.get('/v1/models')
    assert resp.status_code == 200
    data = resp.json()
    assert data['object'] == 'list'
    model_ids = [m['id'] for m in data['data']]
    assert 'local-rag-model' in model_ids


# ---------------------------------------------------------------------------
# X-Request-ID header propagation (metrics_middleware)
# ---------------------------------------------------------------------------

def test_request_id_header_is_propagated_in_response(monkeypatch):
    from tests.conftest import FakeOrchestrator
    monkeypatch.setattr(main_module, 'orch', FakeOrchestrator())
    client = TestClient(app)

    resp = client.get('/health', headers={'X-Request-ID': 'test-req-42'})

    assert resp.headers.get('x-request-id') == 'test-req-42'


def test_request_id_is_generated_when_header_missing(monkeypatch):
    from tests.conftest import FakeOrchestrator
    monkeypatch.setattr(main_module, 'orch', FakeOrchestrator())
    client = TestClient(app)

    resp = client.get('/health')

    assert 'x-request-id' in resp.headers
    assert len(resp.headers['x-request-id']) > 0


# ---------------------------------------------------------------------------
# _dedupe_chart_sections
# ---------------------------------------------------------------------------

def test_dedupe_chart_sections_removes_duplicate_axis():
    text = 'axis:\n- X\npoints/trends:\n1. A\naxis:\n- X\npoints/trends:\n2. B\n'
    result = _dedupe_chart_sections(text)
    assert result.lower().count('axis:') == 1
    assert result.lower().count('points/trends:') == 1


def test_dedupe_chart_sections_preserves_content_lines():
    text = 'legend: Тест\naxis:\n- Время\npoints/trends:\n1. Апрель\n2. Май\n'
    result = _dedupe_chart_sections(text)
    assert '1. Апрель' in result
    assert '2. Май' in result


def test_dedupe_chart_sections_empty_string_returns_empty():
    assert _dedupe_chart_sections('') == ''


def test_dedupe_chart_sections_no_duplicates_unchanged():
    text = 'legend: test\naxis:\n- X\npoints/trends:\n1. A\n'
    result = _dedupe_chart_sections(text)
    assert result.lower().count('axis:') == 1


def test_dedupe_chart_sections_handles_uncertainties():
    text = 'uncertainties:\n- may be\nuncertainties:\n- possibly\n'
    result = _dedupe_chart_sections(text)
    assert result.lower().count('uncertainties:') == 1


# ---------------------------------------------------------------------------
# _apply_visual_answer_fallback
# ---------------------------------------------------------------------------

def test_apply_visual_answer_fallback_returns_original_when_non_empty():
    result = _apply_visual_answer_fallback('Уже есть ответ', [{'ocr_text': 'другой текст'}])
    assert result == 'Уже есть ответ'


def test_apply_visual_answer_fallback_uses_ocr_text_when_answer_empty():
    evidence = [{'ocr_text': 'HTTP 503', 'task_type': 'text', 'visible_facts': []}]
    result = _apply_visual_answer_fallback('   ', evidence)
    assert 'HTTP 503' in result


def test_apply_visual_answer_fallback_returns_empty_when_no_evidence():
    result = _apply_visual_answer_fallback('', [])
    assert result == ''


# ---------------------------------------------------------------------------
# _materialize_data_url — error paths
# ---------------------------------------------------------------------------

def test_materialize_data_url_returns_none_for_non_data_url():
    result = _materialize_data_url('https://example.com/image.png')
    assert result is None


def test_materialize_data_url_returns_none_for_non_base64_encoding():
    result = _materialize_data_url('data:image/png;utf-8,hello')
    assert result is None


def test_materialize_data_url_returns_none_for_invalid_base64(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.settings, 'file_storage_root', str(tmp_path))
    result = _materialize_data_url('data:image/png;base64,NOT_VALID_BASE64!!!')
    assert result is None


def test_materialize_data_url_returns_none_for_unsupported_mime(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.settings, 'file_storage_root', str(tmp_path))
    monkeypatch.setattr(
        main_module.settings,
        'vision_attachment_allowed_mime_types',
        {'image/png', 'image/jpeg'},
    )
    gif_bytes = base64.b64encode(b'GIF89a').decode()
    result = _materialize_data_url(f'data:image/gif;base64,{gif_bytes}')
    assert result is None


def test_materialize_data_url_returns_none_for_oversized_image(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.settings, 'file_storage_root', str(tmp_path))
    monkeypatch.setattr(main_module.settings, 'vision_attachment_max_bytes', 10)
    big_bytes = base64.b64encode(b'X' * 100).decode()
    result = _materialize_data_url(f'data:image/png;base64,{big_bytes}')
    assert result is None


# ---------------------------------------------------------------------------
# _materialize_remote_url — error paths
# ---------------------------------------------------------------------------

def test_materialize_remote_url_returns_none_for_non_http_url():
    result = _materialize_remote_url('/local/path/image.png')
    assert result is None


def test_materialize_remote_url_returns_none_on_http_error(monkeypatch):
    import httpx as _httpx

    def fake_get(url, timeout, follow_redirects):
        raise _httpx.ConnectError('refused')

    monkeypatch.setattr(main_module.httpx, 'get', fake_get)
    result = _materialize_remote_url('https://example.com/image.png')
    assert result is None


def test_materialize_remote_url_returns_none_for_bad_status(monkeypatch, tmp_path):
    import httpx as _httpx

    bad_resp = MagicMock()
    bad_resp.status_code = 404
    monkeypatch.setattr(main_module.httpx, 'get', lambda url, timeout, follow_redirects: bad_resp)
    result = _materialize_remote_url('https://example.com/image.png')
    assert result is None


def test_materialize_remote_url_returns_none_for_oversized_content(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.settings, 'vision_attachment_max_bytes', 5)

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.headers = {'content-type': 'image/png'}
    ok_resp.content = b'X' * 100

    monkeypatch.setattr(main_module.httpx, 'get', lambda url, timeout, follow_redirects: ok_resp)
    monkeypatch.setattr(main_module.settings, 'file_storage_root', str(tmp_path))

    result = _materialize_remote_url('https://example.com/image.png')
    assert result is None


# ---------------------------------------------------------------------------
# _resolve_path_alias
# ---------------------------------------------------------------------------

def test_resolve_path_alias_replaces_matching_prefix(monkeypatch):
    monkeypatch.setattr(
        main_module.settings,
        'vision_attachment_path_aliases',
        '/app/uploads=/data/uploads',
    )
    result = _resolve_path_alias('/app/uploads/file.png')
    assert result == '/data/uploads/file.png'


def test_resolve_path_alias_returns_unchanged_when_no_match(monkeypatch):
    monkeypatch.setattr(
        main_module.settings,
        'vision_attachment_path_aliases',
        '/app/uploads=/data/uploads',
    )
    result = _resolve_path_alias('/other/path/file.png')
    assert result == '/other/path/file.png'


def test_resolve_path_alias_handles_empty_aliases(monkeypatch):
    monkeypatch.setattr(main_module.settings, 'vision_attachment_path_aliases', '')
    result = _resolve_path_alias('/any/path/file.png')
    assert result == '/any/path/file.png'


def test_resolve_path_alias_applies_first_matching_rule(monkeypatch):
    monkeypatch.setattr(
        main_module.settings,
        'vision_attachment_path_aliases',
        '/app/uploads=/data/one;/app=/data/two',
    )
    result = _resolve_path_alias('/app/uploads/test.png')
    assert result == '/data/one/test.png'


# ---------------------------------------------------------------------------
# _looks_like_chart_case
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('question,has_attachments,expected', [
    ('Опиши график', False, True),       # explicit 'график' keyword
    ('Опиши диаграмму', False, True),    # explicit 'диаграм' keyword
    ('Посмотри на axis', True, True),    # weak keyword + has_attachments
    ('Посмотри на axis', False, False),  # weak keyword without attachments
    ('Обычный вопрос', True, False),     # no chart keywords at all
    ('Обычный вопрос', False, False),    # no chart keywords, no attachments
])
def test_looks_like_chart_case(question, has_attachments, expected):
    result = _looks_like_chart_case(question, [], has_attachments=has_attachments)
    assert result is expected
