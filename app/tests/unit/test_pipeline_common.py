from pathlib import Path

import pytest

import src.ingest.pipeline_common as pipeline_common


def test_parse_file_routes_docx_pdf_doc(monkeypatch, tmp_path):
    docx_path = tmp_path / "file.docx"
    pdf_path = tmp_path / "file.pdf"
    doc_path = tmp_path / "file.doc"
    for p in (docx_path, pdf_path, doc_path):
        p.write_text("x")

    monkeypatch.setattr(
        pipeline_common,
        "parse_docx",
        lambda p, source_type='unknown', doc_id=None: {"text": f"docx:{Path(p).name}"},
    )
    monkeypatch.setattr(
        pipeline_common,
        "parse_pdf",
        lambda p, source_type='unknown', doc_id=None: {"text": f"pdf:{Path(p).name}"},
    )
    monkeypatch.setattr(pipeline_common, "convert_doc_to_docx", lambda p: str(tmp_path / "converted.docx"))

    assert pipeline_common._parse_file(docx_path, 'csv_ans_docs')["text"] == "docx:file.docx"
    assert pipeline_common._parse_file(pdf_path, 'csv_ans_docs')["text"] == "pdf:file.pdf"
    assert pipeline_common._parse_file(doc_path, 'csv_ans_docs')["text"] == "docx:converted.docx"


def test_parse_file_rejects_unsupported_extension(tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello")

    with pytest.raises(ValueError, match="Неподдерживаемый формат"):
        pipeline_common._parse_file(txt_path, 'csv_ans_docs')


def test_run_pipeline_processes_supported_files_and_skips_others(monkeypatch, tmp_path):
    supported_a = tmp_path / "a.docx"
    supported_b = tmp_path / "b.pdf"
    ignored = tmp_path / "skip.txt"
    for p in (supported_a, supported_b, ignored):
        p.write_text("data")

    saved_documents = []
    saved_chunks = []
    upserts = []

    class DummyQdrant:
        def ensure_collection(self, source_type, vector_size):
            assert source_type == "csv_ans_docs"
            assert vector_size == 1024

        def upsert_points(self, source_type, points):
            upserts.append((source_type, points))

    class DummyPostgres:
        def save_document(self, doc):
            saved_documents.append(doc)

        def save_chunk(self, chunk):
            saved_chunks.append(chunk)

    class DummyVision:
        def build_document_image_chunks(self, image_assets, *, doc_id, source_type):
            return [
                {
                    'chunk_id': f'{doc_id}_img_0',
                    'text': 'image evidence text',
                    'page_number': 1,
                    'image_paths': [f'/tmp/{doc_id}.png'],
                }
            ]

    monkeypatch.setattr(pipeline_common, "QdrantRepo", DummyQdrant)
    monkeypatch.setattr(pipeline_common, "PostgresRepo", DummyPostgres)
    monkeypatch.setattr(pipeline_common, "VisionService", lambda: DummyVision())
    monkeypatch.setattr(pipeline_common, "file_sha256", lambda _: "hash")
    monkeypatch.setattr(
        pipeline_common,
        "_parse_file",
        lambda path, source_type: {
            "text": f"{path.stem} body",
            "pages": 1,
            "images": [f"{path.stem}.png"],
            "image_assets": [{'path': f"{path.stem}.png", 'page_number': 1}],
        },
    )
    monkeypatch.setattr(
        pipeline_common,
        "chunk_text",
        lambda text, chunk_size=900, overlap=120, strategy="fixed": [f"{text}-c1", f"{text}-c2"],
    )
    monkeypatch.setattr(pipeline_common.EmbeddingClient, "embed", lambda text: [0.1, 0.2])

    result = pipeline_common.run_pipeline(str(tmp_path), "csv_ans_docs")

    assert result["processed_files"] == 2
    assert result["created_points"] == 6
    assert len(saved_documents) == 2
    assert len(saved_chunks) == 6
    assert len(upserts) == 2
    assert {doc["file_name"] for doc in saved_documents} == {"a.docx", "b.pdf"}
    assert all(chunk["source_type"] == "csv_ans_docs" for chunk in saved_chunks)
    assert result["diagnostics"] == {
        "total_image_assets": 2,
        "total_image_points": 2,
        "total_image_assets_without_chunks": 0,
    }


def test_run_pipeline_sets_page_number_for_pdf_text_chunks(monkeypatch, tmp_path):
    supported_pdf = tmp_path / "manual.pdf"
    supported_pdf.write_text("data")

    saved_chunks = []

    class DummyQdrant:
        def ensure_collection(self, source_type, vector_size):
            pass

        def upsert_points(self, source_type, points):
            pass

    class DummyPostgres:
        def save_document(self, doc):
            pass

        def save_chunk(self, chunk):
            saved_chunks.append(chunk)

    class DummyVision:
        def build_document_image_chunks(self, image_assets, *, doc_id, source_type):
            return []

    monkeypatch.setattr(pipeline_common, "QdrantRepo", DummyQdrant)
    monkeypatch.setattr(pipeline_common, "PostgresRepo", DummyPostgres)
    monkeypatch.setattr(pipeline_common, "VisionService", lambda: DummyVision())
    monkeypatch.setattr(pipeline_common, "file_sha256", lambda _: "hash")
    monkeypatch.setattr(
        pipeline_common,
        "_parse_file",
        lambda path, source_type: {
            "text": "page1\npage2",
            "page_texts": [
                {"page_number": 1, "text": "first page text"},
                {"page_number": 2, "text": "second page text"},
            ],
            "pages": 2,
            "images": [],
            "image_assets": [],
        },
    )
    monkeypatch.setattr(
        pipeline_common,
        "chunk_text",
        lambda text, chunk_size=900, overlap=120, strategy="fixed": [f"{text}-chunk"],
    )
    monkeypatch.setattr(pipeline_common.EmbeddingClient, "embed", lambda text: [0.1, 0.2])

    pipeline_common.run_pipeline(str(tmp_path), "csv_ans_docs")

    text_chunk_pages = [c["page_number"] for c in saved_chunks if c["chunk_id"].endswith("_ch_0") or c["chunk_id"].endswith("_ch_1")]
    assert text_chunk_pages == [1, 2]


def test_stable_point_id_is_deterministic():
    left = pipeline_common._stable_point_id("csv_ans_docs", "vision_regression_marker_ch_0")
    right = pipeline_common._stable_point_id("csv_ans_docs", "vision_regression_marker_ch_0")
    changed = pipeline_common._stable_point_id("csv_ans_docs", "vision_regression_marker_ch_1")

    assert isinstance(left, int)
    assert left == right
    assert left != changed


def test_run_pipeline_tracks_missing_image_chunks_diagnostics(monkeypatch, tmp_path):
    supported_pdf = tmp_path / "regulation.pdf"
    supported_pdf.write_text("data")

    class DummyQdrant:
        def ensure_collection(self, source_type, vector_size):
            pass

        def upsert_points(self, source_type, points):
            pass

    class DummyPostgres:
        def save_document(self, doc):
            pass

        def save_chunk(self, chunk):
            pass

    class DummyVision:
        def build_document_image_chunks(self, image_assets, *, doc_id, source_type):
            return []

    monkeypatch.setattr(pipeline_common, "QdrantRepo", DummyQdrant)
    monkeypatch.setattr(pipeline_common, "PostgresRepo", DummyPostgres)
    monkeypatch.setattr(pipeline_common, "VisionService", lambda: DummyVision())
    monkeypatch.setattr(pipeline_common, "file_sha256", lambda _: "hash")
    monkeypatch.setattr(
        pipeline_common,
        "_parse_file",
        lambda path, source_type: {
            "text": "sample text",
            "pages": 1,
            "images": ["raw.jb2"],
            "image_assets": [{'path': "raw.jb2", 'page_number': 1}],
        },
    )
    monkeypatch.setattr(
        pipeline_common,
        "chunk_text",
        lambda text, chunk_size=900, overlap=120, strategy="fixed": ["sample-chunk"],
    )
    monkeypatch.setattr(pipeline_common.EmbeddingClient, "embed", lambda text: [0.1, 0.2])

    result = pipeline_common.run_pipeline(str(tmp_path), "internal_regulations")

    assert result["diagnostics"] == {
        "total_image_assets": 1,
        "total_image_points": 0,
        "total_image_assets_without_chunks": 1,
    }
