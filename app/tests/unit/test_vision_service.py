from pathlib import Path

from src.api.schemas import AttachmentItem
from src.vision.service import VisionService


def test_analyze_attachments_returns_evidence_even_without_ocr(monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'fake')

    service = VisionService()
    monkeypatch.setattr(service, '_run_ocr', lambda path: 'HTTP 500 Internal Server Error')

    evidence = service.analyze_attachments([AttachmentItem(image_path=str(image))], question='Что случилось?')

    assert len(evidence) == 1
    assert evidence[0].image_path == str(image)
    assert 'HTTP 500' in evidence[0].ocr_text
    assert evidence[0].confidence > 0.5


def test_build_document_image_chunks_uses_ocr_and_summary(monkeypatch):
    service = VisionService()
    monkeypatch.setattr(service, '_run_ocr', lambda path: 'Access denied')

    chunks = service.build_document_image_chunks(
        [{'path': '/tmp/img-1.png', 'page_number': 5}],
        doc_id='DOC-1',
        source_type='csv_ans_docs',
    )

    assert len(chunks) == 1
    assert chunks[0]['chunk_id'] == 'DOC-1_img_0'
    assert chunks[0]['page_number'] == 5
    assert 'Access denied' in chunks[0]['text']
