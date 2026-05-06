import json
from unittest.mock import MagicMock

import pytest

from src.storage.postgres_repo import PostgresRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo_with_cursor(monkeypatch, *, fetchone=None):
    """Return (repo, conn_mock, cursor_mock) with psycopg.connect mocked."""
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = fetchone

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor

    monkeypatch.setattr('src.storage.postgres_repo.connect', lambda dsn: conn)
    return PostgresRepo(), conn, cursor


# ---------------------------------------------------------------------------
# save_document
# ---------------------------------------------------------------------------

def test_save_document_executes_insert_with_correct_params(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch)

    repo.save_document({
        'doc_id': 'DOC-1',
        'source_type': 'csv_ans_docs',
        'file_name': 'doc1.pdf',
        'file_hash': 'abc123',
        'pages': 10,
    })

    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert 'INSERT INTO documents' in sql
    assert 'ON CONFLICT DO NOTHING' in sql
    assert params == ('DOC-1', 'csv_ans_docs', 'doc1.pdf', 'abc123', 10)
    conn.commit.assert_called_once()


def test_save_document_passes_none_pages(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch)

    repo.save_document({
        'doc_id': 'DOC-2',
        'source_type': 'internal_regulations',
        'file_name': 'reg.docx',
        'file_hash': 'def456',
    })

    _, params = cursor.execute.call_args[0]
    assert params[4] is None  # pages not provided → None


# ---------------------------------------------------------------------------
# save_chunk
# ---------------------------------------------------------------------------

def test_save_chunk_executes_insert_with_correct_params(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch)

    repo.save_chunk({
        'doc_id': 'DOC-1',
        'source_type': 'csv_ans_docs',
        'chunk_id': 'DOC-1_ch_0',
        'page_number': 3,
        'text_preview': 'Текст чанка',
        'image_paths': ['/tmp/img.png'],
    })

    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert 'INSERT INTO chunks' in sql
    assert 'ON CONFLICT DO NOTHING' in sql
    assert params[0] == 'DOC-1'
    assert params[1] == 'csv_ans_docs'
    assert params[2] == 'DOC-1_ch_0'
    assert params[3] == 3
    assert params[4] == 'Текст чанка'
    assert json.loads(params[5]) == ['/tmp/img.png']
    conn.commit.assert_called_once()


def test_save_chunk_truncates_text_preview_at_500_chars(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch)
    long_text = 'А' * 600

    repo.save_chunk({
        'doc_id': 'DOC-1',
        'source_type': 'csv_ans_docs',
        'chunk_id': 'DOC-1_ch_0',
        'text_preview': long_text,
        'image_paths': [],
    })

    _, params = cursor.execute.call_args[0]
    stored_preview = params[4]
    assert len(stored_preview) == 500


def test_save_chunk_empty_image_paths_stored_as_json_array(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch)

    repo.save_chunk({
        'doc_id': 'DOC-1',
        'source_type': 'csv_ans_docs',
        'chunk_id': 'DOC-1_ch_0',
        'image_paths': [],
    })

    _, params = cursor.execute.call_args[0]
    assert json.loads(params[5]) == []


# ---------------------------------------------------------------------------
# get_document_file_name
# ---------------------------------------------------------------------------

def test_get_document_file_name_returns_name_when_found(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=('my_doc.pdf',))

    result = repo.get_document_file_name('csv_ans_docs', 'DOC-1')

    assert result == 'my_doc.pdf'
    sql, params = cursor.execute.call_args[0]
    assert 'SELECT file_name' in sql
    assert params == ('csv_ans_docs', 'DOC-1')


def test_get_document_file_name_returns_none_when_not_found(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=None)

    result = repo.get_document_file_name('csv_ans_docs', 'MISSING')

    assert result is None


# ---------------------------------------------------------------------------
# document_exists
# ---------------------------------------------------------------------------

def test_document_exists_returns_true_when_found(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=(1,))

    assert repo.document_exists('csv_ans_docs', 'DOC-1') is True


def test_document_exists_returns_false_when_not_found(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=None)

    assert repo.document_exists('csv_ans_docs', 'MISSING') is False


# ---------------------------------------------------------------------------
# chunk_count_for_document
# ---------------------------------------------------------------------------

def test_chunk_count_returns_integer_count(monkeypatch):
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=(7,))

    count = repo.chunk_count_for_document('csv_ans_docs', 'DOC-1')

    assert count == 7
    sql, params = cursor.execute.call_args[0]
    assert 'SELECT COUNT(*)' in sql
    assert params == ('csv_ans_docs', 'DOC-1')


def test_chunk_count_returns_zero_when_fetchone_returns_none(monkeypatch):
    # SELECT COUNT(*) always returns a row, but guard should handle None safely
    repo, conn, cursor = _make_repo_with_cursor(monkeypatch, fetchone=None)

    count = repo.chunk_count_for_document('csv_ans_docs', 'EMPTY_DOC')

    assert count == 0
