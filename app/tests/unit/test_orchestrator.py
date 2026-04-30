import pytest

from src.api.schemas import AskRequest, AttachmentItem
from src.core.settings import settings
from src.rag.orchestrator import RagOrchestrator


@pytest.fixture(autouse=True)
def _isolate_rag_trace_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'rag_ui_trace_enabled', True)
    monkeypatch.setattr(settings, 'rag_ui_trace_dir', str(tmp_path / 'rag_ui_traces'))


class _NoContextRetriever:
    def retrieve(self, question, top_k, scope):
        return []

    def retrieve_with_trace(self, question, top_k, scope):
        return [], {'timings_sec': {'embedding': 0.0, 'retrieval': 0.0, 'rerank': 0.0, 'total': 0.0}}


class _NeverCalledLlm:
    def generate(self, prompt, max_tokens=512, temperature=0.1):
        raise AssertionError('LLM should not be called when contexts are empty')


class _NoEvidenceVision:
    def analyze_attachments(self, attachments, question):
        return []


def test_orchestrator_returns_fallback_when_no_contexts_and_no_visual_evidence():
    orch = RagOrchestrator()
    orch.retriever = _NoContextRetriever()
    orch.llm = _NeverCalledLlm()
    orch.vision = _NoEvidenceVision()

    payload = AskRequest(question='Привет', top_k=8, scope='all')
    response = orch.answer(payload)

    assert 'Не нашёл релевантных данных' in response.answer
    assert response.sources == []
    assert response.images == []
    assert response.visual_evidence == []


class _VisionMustNotBeCalled:
    def analyze_attachments(self, attachments, question):
        raise AssertionError('Vision should not be called when attachments are empty')


def test_orchestrator_skips_vision_when_no_attachments():
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _VisionMustNotBeCalled()

    payload = AskRequest(question='Проверь без вложений', top_k=8, scope='all')
    response = orch.answer(payload)

    assert response.visual_evidence == []


class _RetrieverWithOneContext:
    def retrieve(self, question, top_k, scope):
        return [
            {
                'doc_id': 'DOC-123',
                'source_type': 'csv_ans_docs',
                'page_number': 2,
                'chunk_id': 'DOC-123_ch_0',
                'score': 0.91,
                'image_paths': [],
                'text': 'Тестовый фрагмент',
            }
        ]

    def retrieve_with_trace(self, question, top_k, scope):
        contexts = self.retrieve(question, top_k, scope)
        return contexts, {
            'query': {'question': question, 'scope': scope, 'top_k': top_k, 'candidate_limit': top_k},
            'timings_sec': {'embedding': 0.001, 'retrieval': 0.002, 'rerank': 0.0, 'total': 0.003},
            'raw_by_collection': {'csv_ans_docs': []},
            'combined_sorted': contexts,
            'deduped_count': len(contexts),
            'filtered_count': len(contexts),
            'returned_count': len(contexts),
            'reranker': {'enabled': False, 'applied': False, 'min_score': 0.25},
            'contexts_used_for_prompt': contexts,
        }


class _LlmWithFixedAnswer:
    def generate(self, prompt, max_tokens=512, temperature=0.1, trace=None):
        if trace is not None:
            trace["answer"] = "Тестовый ответ"
        return 'Тестовый ответ'


class _VisionWithEvidence:
    def analyze_attachments(self, attachments, question):
        if not attachments:
            return []
        return [
            {
                'image_path': attachments[0].image_path,
                'ocr_text': 'Ошибка 500',
                'summary': 'Найдена ошибка',
                'confidence': 0.8,
            }
        ]


def test_orchestrator_sets_download_url_for_source():
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _NoEvidenceVision()

    payload = AskRequest(question='Как провести отказ?', top_k=8, scope='all')
    response = orch.answer(payload)

    assert len(response.sources) == 1
    assert response.sources[0].download_url == '/sources/csv_ans_docs/DOC-123/download'


def test_orchestrator_uses_visual_evidence_from_attachments():
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _VisionWithEvidence()

    payload = AskRequest(
        question='Проверь ошибку',
        top_k=8,
        scope='all',
        attachments=[AttachmentItem(image_path='/tmp/error.png')],
    )
    response = orch.answer(payload)

    assert response.visual_evidence
    assert response.visual_evidence[0].image_path == '/tmp/error.png'


def test_orchestrator_writes_trace_card():
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _NoEvidenceVision()
    captured = {}

    class _TraceWriter:
        def write(self, card):
            captured["card"] = card
            return {"json_path": "/tmp/a.json", "markdown_path": "/tmp/a.md"}

    orch.trace_writer = _TraceWriter()

    payload = AskRequest(question='Проверь трассировку', top_k=8, scope='all')
    orch.answer(payload)

    assert "card" in captured
    assert captured["card"]["stages"]["prompt"]["final_prompt"]
    assert captured["card"]["stages"]["retrieval"]["combined_sorted"]
    assert captured["card"]["aggregate_timings_sec"]["total"] >= 0


def test_orchestrator_returns_response_when_trace_dir_mkdir_permission_error(monkeypatch):
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _NoEvidenceVision()

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError('mkdir denied')

    monkeypatch.setattr('src.rag.trace_card.Path.mkdir', _raise_permission_error)

    payload = AskRequest(question='Проверь mkdir error', top_k=8, scope='all')
    response = orch.answer(payload)

    assert response.answer == 'Тестовый ответ'
    assert len(response.sources) == 1


def test_orchestrator_returns_response_when_trace_write_permission_error(monkeypatch):
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()
    orch.vision = _NoEvidenceVision()

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError('write denied')

    monkeypatch.setattr('src.rag.trace_card.Path.write_text', _raise_permission_error)

    payload = AskRequest(question='Проверь write error', top_k=8, scope='all')
    response = orch.answer(payload)

    assert response.answer == 'Тестовый ответ'
    assert len(response.sources) == 1


def test_orchestrator_render_visual_answer_handles_dicts_and_models():
    orch = RagOrchestrator()

    class _Item:
        def model_dump(self):
            return {
                'image_path': '/tmp/a.png',
                'summary': 'Найден предупреждающий баннер',
                'ocr_text': 'ERROR 503',
                'task_type': 'text',
            }

    answer = orch._render_visual_answer([_Item(), {'summary': 'График продаж', 'task_type': 'chart'}])

    assert 'Найден предупреждающий баннер' in answer
    assert 'ERROR 503' in answer
    assert 'График продаж' in answer
