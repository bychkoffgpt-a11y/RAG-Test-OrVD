from fastapi.testclient import TestClient

from src.main import app
import src.api.sources as sources_module


class _DummyPostgresRepo:
    def __init__(self, file_name: str | None):
        self.file_name = file_name

    def get_document_file_name(self, source_type: str, doc_id: str) -> str | None:
        return self.file_name


def test_sources_download_returns_file(monkeypatch, tmp_path):
    inbox_dir = tmp_path / 'inbox' / 'csv_ans_docs'
    inbox_dir.mkdir(parents=True)
    doc_path = inbox_dir / 'Инструкция.docx'
    doc_path.write_text('test-content', encoding='utf-8')

    monkeypatch.setattr(sources_module, 'postgres', _DummyPostgresRepo(file_name='Инструкция.docx'))
    monkeypatch.setattr(sources_module.settings, 'file_storage_root', str(tmp_path))

    client = TestClient(app)
    response = client.get('/sources/csv_ans_docs/DOC-1/download')

    assert response.status_code == 200
    assert response.content == b'test-content'
    assert 'attachment' in response.headers.get('content-disposition', '')


def test_sources_download_returns_404_for_unknown_document(monkeypatch):
    monkeypatch.setattr(sources_module, 'postgres', _DummyPostgresRepo(file_name=None))

    client = TestClient(app)
    response = client.get('/sources/csv_ans_docs/UNKNOWN/download')

    assert response.status_code == 404
