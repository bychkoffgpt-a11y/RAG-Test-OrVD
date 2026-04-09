from pathlib import Path

import pytest

import src.ingest.pipeline_common as pipeline_common


def test_parse_file_routes_docx_pdf_doc(monkeypatch, tmp_path):
    docx_path = tmp_path / "file.docx"
    pdf_path = tmp_path / "file.pdf"
    doc_path = tmp_path / "file.doc"
    for p in (docx_path, pdf_path, doc_path):
        p.write_text("x")

    monkeypatch.setattr(pipeline_common, "parse_docx", lambda p: {"text": f"docx:{Path(p).name}"})
    monkeypatch.setattr(pipeline_common, "parse_pdf", lambda p: {"text": f"pdf:{Path(p).name}"})
    monkeypatch.setattr(pipeline_common, "convert_doc_to_docx", lambda p: str(tmp_path / "converted.docx"))

    assert pipeline_common._parse_file(docx_path)["text"] == "docx:file.docx"
    assert pipeline_common._parse_file(pdf_path)["text"] == "pdf:file.pdf"
    assert pipeline_common._parse_file(doc_path)["text"] == "docx:converted.docx"


def test_parse_file_rejects_unsupported_extension(tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello")

    with pytest.raises(ValueError, match="Неподдерживаемый формат"):
        pipeline_common._parse_file(txt_path)


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

    monkeypatch.setattr(pipeline_common, "QdrantRepo", DummyQdrant)
    monkeypatch.setattr(pipeline_common, "PostgresRepo", DummyPostgres)
    monkeypatch.setattr(pipeline_common, "file_sha256", lambda _: "hash")
    monkeypatch.setattr(
        pipeline_common,
        "_parse_file",
        lambda path: {
            "text": f"{path.stem} body",
            "pages": 1,
            "images": [f"{path.stem}.png"],
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
    assert result["created_points"] == 4
    assert len(saved_documents) == 2
    assert len(saved_chunks) == 4
    assert len(upserts) == 2
    assert {doc["file_name"] for doc in saved_documents} == {"a.docx", "b.pdf"}
    assert all(chunk["source_type"] == "csv_ans_docs" for chunk in saved_chunks)
