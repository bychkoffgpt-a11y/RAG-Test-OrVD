"""
Integration tests for /ingest/a/run and /ingest/b/run endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app
import src.api.ingest_a as ingest_a_module
import src.api.ingest_b as ingest_b_module


_BASE_RESULT = {
    'source_type': 'csv_ans_docs',
    'processed_files': 3,
    'created_points': 12,
    'diagnostics': {
        'total_image_assets': 4,
        'total_image_points': 3,
        'total_image_assets_without_chunks': 1,
    },
    'message': 'Индексация csv_ans_docs завершена',
}


# ---------------------------------------------------------------------------
# /ingest/a/run
# ---------------------------------------------------------------------------

def test_ingest_a_run_returns_200(monkeypatch):
    monkeypatch.setattr(ingest_a_module, 'run_pipeline_a', lambda path: {**_BASE_RESULT})
    client = TestClient(app)

    resp = client.post('/ingest/a/run')

    assert resp.status_code == 200


def test_ingest_a_run_returns_correct_response_body(monkeypatch):
    monkeypatch.setattr(ingest_a_module, 'run_pipeline_a', lambda path: {**_BASE_RESULT})
    client = TestClient(app)

    resp = client.post('/ingest/a/run')
    data = resp.json()

    assert data['source_type'] == 'csv_ans_docs'
    assert data['processed_files'] == 3
    assert data['created_points'] == 12
    assert data['message'] == 'Индексация csv_ans_docs завершена'
    assert data['diagnostics']['total_image_assets'] == 4


def test_ingest_a_calls_pipeline_with_correct_path(monkeypatch):
    called_with = {}

    def fake_pipeline(path: str) -> dict:
        called_with['path'] = path
        return {**_BASE_RESULT}

    monkeypatch.setattr(ingest_a_module, 'run_pipeline_a', fake_pipeline)
    client = TestClient(app)

    client.post('/ingest/a/run')

    assert called_with.get('path') == '/data/inbox/csv_ans_docs'


def test_ingest_a_run_zero_files_is_valid(monkeypatch):
    result = {
        'source_type': 'csv_ans_docs',
        'processed_files': 0,
        'created_points': 0,
        'diagnostics': {'total_image_assets': 0, 'total_image_points': 0, 'total_image_assets_without_chunks': 0},
        'message': 'Индексация csv_ans_docs завершена',
    }
    monkeypatch.setattr(ingest_a_module, 'run_pipeline_a', lambda path: result)
    client = TestClient(app)

    resp = client.post('/ingest/a/run')

    assert resp.status_code == 200
    assert resp.json()['processed_files'] == 0


# ---------------------------------------------------------------------------
# /ingest/b/run
# ---------------------------------------------------------------------------

def test_ingest_b_run_returns_200(monkeypatch):
    result = {
        'source_type': 'internal_regulations',
        'processed_files': 5,
        'created_points': 20,
        'diagnostics': {'total_image_assets': 0, 'total_image_points': 0, 'total_image_assets_without_chunks': 0},
        'message': 'Индексация internal_regulations завершена',
    }
    monkeypatch.setattr(ingest_b_module, 'run_pipeline_b', lambda path: result)
    client = TestClient(app)

    resp = client.post('/ingest/b/run')

    assert resp.status_code == 200


def test_ingest_b_calls_pipeline_with_correct_path(monkeypatch):
    called_with = {}

    def fake_pipeline(path: str) -> dict:
        called_with['path'] = path
        return {
            'source_type': 'internal_regulations',
            'processed_files': 1,
            'created_points': 2,
            'diagnostics': {},
            'message': 'done',
        }

    monkeypatch.setattr(ingest_b_module, 'run_pipeline_b', fake_pipeline)
    client = TestClient(app)

    client.post('/ingest/b/run')

    assert called_with.get('path') == '/data/inbox/internal_regulations'


def test_ingest_b_run_returns_correct_source_type(monkeypatch):
    result = {
        'source_type': 'internal_regulations',
        'processed_files': 2,
        'created_points': 8,
        'diagnostics': {},
        'message': 'Индексация internal_regulations завершена',
    }
    monkeypatch.setattr(ingest_b_module, 'run_pipeline_b', lambda path: result)
    client = TestClient(app)

    resp = client.post('/ingest/b/run')

    assert resp.json()['source_type'] == 'internal_regulations'
