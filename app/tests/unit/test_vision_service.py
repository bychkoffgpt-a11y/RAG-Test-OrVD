from pathlib import Path
import sys
from unittest.mock import Mock

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


def test_build_document_image_chunks_not_blocked_by_runtime_vision_toggle(monkeypatch):
    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_enabled', False, raising=False)
    monkeypatch.setattr('src.vision.service.settings.vision_ingest_enabled', True, raising=False)
    monkeypatch.setattr(service, '_run_ocr', lambda path: 'OCR text')

    chunks = service.build_document_image_chunks(
        [{'path': '/tmp/img-2.png', 'page_number': 1}],
        doc_id='DOC-2',
        source_type='csv_ans_docs',
    )

    assert len(chunks) == 1
    assert chunks[0]['chunk_id'] == 'DOC-2_img_0'


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


def test_run_ocr_skips_unsupported_jbig2_extension(tmp_path, monkeypatch):
    image = tmp_path / 'scan.jb2'
    image.write_bytes(b'fake')
    service = VisionService()
    ocr_mock = Mock()
    monkeypatch.setattr(service, '_get_ocr_client', lambda: ocr_mock)

    result = service._run_ocr(str(image))

    assert result == ''
    ocr_mock.ocr.assert_not_called()


def test_runtime_mode_vlm_uses_vlm_extractor(monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'fake')
    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_runtime_mode', 'vlm', raising=False)
    monkeypatch.setattr(service, '_run_vlm', lambda path, question: 'Detected app error screen')
    ocr_mock = Mock()
    monkeypatch.setattr(service, '_run_ocr', ocr_mock)

    evidence = service.analyze_attachments([AttachmentItem(image_path=str(image))], question='Что на экране?')

    assert len(evidence) == 1
    assert evidence[0].summary
    assert evidence[0].ocr_text == ''
    ocr_mock.assert_not_called()


def test_ingest_mode_vlm_builds_vlm_chunks(monkeypatch):
    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_ingest_mode', 'vlm', raising=False)
    monkeypatch.setattr(service, '_run_vlm', lambda path, question: 'Screenshot of settings panel')
    ocr_mock = Mock()
    monkeypatch.setattr(service, '_run_ocr', ocr_mock)

    chunks = service.build_document_image_chunks(
        [{'path': '/tmp/img-vlm.png', 'page_number': 7}],
        doc_id='DOC-VLM',
        source_type='internal_regulations',
    )

    assert len(chunks) == 1
    assert 'VLM:' in chunks[0]['text']
    assert 'Screenshot of settings panel' in chunks[0]['text']
    ocr_mock.assert_not_called()
