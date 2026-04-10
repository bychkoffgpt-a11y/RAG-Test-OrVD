from pathlib import Path
import sys

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


def test_resolve_ocr_use_gpu_auto_prefers_cpu_when_paddle_missing(monkeypatch):
    monkeypatch.setattr('src.vision.service.settings.vision_ocr_device', 'auto', raising=False)
    monkeypatch.delitem(sys.modules, 'paddle', raising=False)

    assert VisionService._resolve_ocr_use_gpu() is False


def test_resolve_ocr_use_gpu_cuda_raises_without_cuda_runtime(monkeypatch):
    class _FakePaddle:
        @staticmethod
        def is_compiled_with_cuda():
            return False

    monkeypatch.setattr('src.vision.service.settings.vision_ocr_device', 'cuda', raising=False)
    monkeypatch.setitem(sys.modules, 'paddle', _FakePaddle())

    try:
        VisionService._resolve_ocr_use_gpu()
        assert False, 'Expected RuntimeError for missing CUDA runtime'
    except RuntimeError as exc:
        assert 'CUDA device requested for OCR' in str(exc)
