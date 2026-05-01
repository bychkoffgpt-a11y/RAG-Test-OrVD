from pathlib import Path
import sys
from unittest.mock import Mock
import numpy as np

from src.api.schemas import AttachmentItem
from src.vision.service import VisionService


def test_analyze_attachments_returns_evidence_even_without_ocr(monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'fake')

    service = VisionService()
    monkeypatch.setattr(service, '_run_ocr', lambda path: 'HTTP 500 Internal Server Error')

    evidence = service.analyze_attachments(
        [AttachmentItem(image_path=str(image), source_url='https://example.com/screen.png?text=abc')],
        question='Что случилось?',
    )

    assert len(evidence) == 1
    assert evidence[0].image_path == str(image)
    assert evidence[0].source_url == 'https://example.com/screen.png?text=abc'
    assert 'HTTP 500' in evidence[0].ocr_text
    assert evidence[0].confidence > 0.5


def test_build_summary_uses_basename_without_query():
    summary = VisionService._build_summary('/tmp/screen.png?text=abc', 'error 500', mode='ocr')
    assert 'Файл: screen.png' in summary


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
    monkeypatch.setattr(service, '_run_vlm', lambda path, question, deadline=None, allow_raw_fallback=False: 'Detected app error screen')
    ocr_mock = Mock()
    monkeypatch.setattr(service, '_run_ocr', ocr_mock)

    evidence = service.analyze_attachments([AttachmentItem(image_path=str(image))], question='Что на экране?')

    assert len(evidence) == 1
    assert evidence[0].summary
    assert evidence[0].ocr_text == 'Detected app error screen'
    assert evidence[0].vlm_output_format == 'raw'
    ocr_mock.assert_not_called()


def test_ingest_mode_vlm_builds_vlm_chunks(monkeypatch):
    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_ingest_mode', 'vlm', raising=False)
    monkeypatch.setattr(service, '_run_vlm', lambda path, question, deadline=None, allow_raw_fallback=False: 'Screenshot of settings panel')
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


def test_analyze_attachments_respects_runtime_max_images(monkeypatch, tmp_path):
    img1 = tmp_path / 'one.png'
    img2 = tmp_path / 'two.png'
    img1.write_bytes(b'fake')
    img2.write_bytes(b'fake')

    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_runtime_max_images', 1, raising=False)
    monkeypatch.setattr(service, '_run_ocr', lambda path: f'OCR:{Path(path).name}')

    evidence = service.analyze_attachments(
        [AttachmentItem(image_path=str(img1)), AttachmentItem(image_path=str(img2))],
        question='Проверь',
    )

    assert len(evidence) == 1
    assert evidence[0].image_path == str(img1)


def test_analyze_single_image_skips_large_image(monkeypatch, tmp_path):
    image = tmp_path / 'large.png'
    image.write_bytes(b'fake')

    service = VisionService()
    monkeypatch.setattr('src.vision.service.settings.vision_runtime_max_image_pixels', 10, raising=False)
    monkeypatch.setattr(service, '_image_exceeds_pixels_limit', lambda *_args, **_kwargs: True)
    run_ocr_mock = Mock()
    monkeypatch.setattr(service, '_run_ocr', run_ocr_mock)

    evidence = service.analyze_attachments([AttachmentItem(image_path=str(image))], question='Проверь')

    assert len(evidence) == 1
    assert evidence[0].confidence == 0.0
    assert 'превышен лимит' in evidence[0].summary
    run_ocr_mock.assert_not_called()


def test_parse_vlm_json_valid_payload():
    service = VisionService()
    parsed = service._parse_vlm_json('{"visible_facts":["Error 500"],"uncertain_facts":["button may be disabled"],"not_visible":[],"confidence":0.9}')
    assert parsed is not None
    assert parsed.visible_facts == ['Error 500']




def test_parse_vlm_json_markdown_json_block():
    service = VisionService()
    raw = '''```json
{"visible_facts":["Error 500"],"uncertain_facts":[],"not_visible":[],"confidence":0.8}
```'''
    parsed = service._parse_vlm_json(raw)
    assert parsed is not None
    assert parsed.visible_facts == ['Error 500']


def test_parse_vlm_json_text_with_trailing_json():
    service = VisionService()
    raw = '''Model answer summary:
The UI shows an error.
{"visible_facts":["Error 500"],"uncertain_facts":[],"not_visible":[],"confidence":0.8}'''
    parsed = service._parse_vlm_json(raw)
    assert parsed is not None
    assert parsed.visible_facts == ['Error 500']


def test_parse_vlm_json_invalid_schema_objects_list():
    service = VisionService()
    raw = '{"visible_facts":[{"k":"v"}],"uncertain_facts":[],"not_visible":[],"confidence":0.8}'
    parsed = service._parse_vlm_json(raw)
    assert parsed is None

def test_run_vlm_repairs_invalid_json(monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'fake')
    service = VisionService()

    class DummyProcessor:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            return messages[0]['content'][1]['text']

        def __call__(self, text, images, return_tensors='pt', padding=True):
            return {'input_ids': np.array([[11, 12, 13]])}

        def batch_decode(self, generated, **kwargs):
            payload = tuple(generated[0].tolist())
            mapping = {
                (100, 101): 'user: q assistant: not-json',
                (200, 201): '{"visible_facts":["ok"],"uncertain_facts":[],"not_visible":[],"confidence":0.7}',
            }
            return [mapping[payload]]

    class DummyModel:
        def __init__(self):
            self.calls = 0

        def generate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return np.array([[11, 12, 13, 100, 101]])
            return np.array([[11, 12, 13, 200, 201]])

    class DummyTorch:
        class _NoGrad:
            def __enter__(self):
                return None
            def __exit__(self, exc_type, exc, tb):
                return False
        @staticmethod
        def no_grad():
            return DummyTorch._NoGrad()

    monkeypatch.setattr('src.vision.service.Path.exists', lambda self: True)
    monkeypatch.setattr(service, '_get_vlm_client', lambda: (DummyProcessor(), DummyModel(), 'cpu'))
    monkeypatch.setitem(sys.modules, 'torch', DummyTorch())
    monkeypatch.setitem(sys.modules, 'PIL', type('P', (), {'Image': type('I', (), {'open': staticmethod(lambda *_: type('Img', (), {'convert': lambda self, _: self})())})})())

    result = service._run_vlm(str(image), question='q', deadline=None)
    assert 'visible_facts' in result


def test_run_vlm_runtime_fallback_keeps_raw_text_when_json_invalid(monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'fake')
    service = VisionService()

    class DummyProcessor:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            return messages[0]['content'][1]['text']

        def __call__(self, text, images, return_tensors='pt', padding=True):
            return {'input_ids': np.array([[21, 22]])}

        def batch_decode(self, generated, **kwargs):
            payload = tuple(generated[0].tolist())
            mapping = {
                (111,): 'first non-json output',
                (222,): 'second still invalid',
            }
            return [mapping[payload]]

    class DummyModel:
        def __init__(self):
            self.calls = 0

        def generate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return np.array([[21, 22, 111]])
            return np.array([[21, 22, 222]])

    class DummyTorch:
        class _NoGrad:
            def __enter__(self):
                return None
            def __exit__(self, exc_type, exc, tb):
                return False
        @staticmethod
        def no_grad():
            return DummyTorch._NoGrad()

    monkeypatch.setattr('src.vision.service.Path.exists', lambda self: True)
    monkeypatch.setattr(service, '_get_vlm_client', lambda: (DummyProcessor(), DummyModel(), 'cpu'))
    monkeypatch.setitem(sys.modules, 'torch', DummyTorch())
    monkeypatch.setitem(sys.modules, 'PIL', type('P', (), {'Image': type('I', (), {'open': staticmethod(lambda *_: type('Img', (), {'convert': lambda self, _: self})())})})())

    result = service._run_vlm(str(image), question='q', deadline=None, allow_raw_fallback=True)
    assert result == 'second still invalid'


def test_decode_generated_tail_removes_prompt_tokens_and_dialog_markup():
    class DummyProcessor:
        def batch_decode(self, generated, **kwargs):
            payload = tuple(generated[0].tolist())
            assert payload == (301, 302)
            return ['assistant: Чистый ответ модели']

    generated = np.array([[1, 2, 3, 301, 302]])
    result = VisionService._decode_generated_tail(DummyProcessor(), generated, prompt_len=3)

    assert result == 'assistant: Чистый ответ модели'


def test_normalize_for_scoring_handles_numbers_dates_units():
    text = '  Цена: 1 000 и 1,000 кг, дата 01/02/2024 — OK  '
    normalized = VisionService._normalize_for_scoring(text)
    assert '1000' in normalized
    assert '2024-02-01' in normalized
    assert 'kg' in normalized


def test_detect_task_type_routes_chart_sign_text():
    assert VisionService._detect_task_type(question='Опиши chart legend и axis', image_path='a.png') == 'chart'
    assert VisionService._detect_task_type(question='Прочитай warning sign', image_path='a.png') == 'sign'
    assert VisionService._detect_task_type(question='Извлеки текст таблицы', image_path='a.png') == 'text'


def test_compose_structured_text_limits_chart_points(monkeypatch):
    service = VisionService()
    raw = '{"visible_facts":["A:1","B:2"],"uncertain_facts":["C maybe 3"],"not_visible":[],"confidence":0.9}'
    out = service._compose_structured_text(raw)
    assert 'a:1' in out and 'b:2' in out
    assert 'c maybe 3' in out


def test_parse_vlm_json_rejects_duplicate_fact_across_sections():
    service = VisionService()
    parsed = service._parse_vlm_json(
        '{"visible_facts":["Error 500"],"uncertain_facts":[],"not_visible":["error 500"],"confidence":0.5}'
    )
    assert parsed is None


def test_parse_vlm_json_rejects_not_visible_with_high_confidence():
    service = VisionService()
    parsed = service._parse_vlm_json(
        '{"visible_facts":["Error 500"],"uncertain_facts":[],"not_visible":["нечитаемо"],"confidence":0.9}'
    )
    assert parsed is None
