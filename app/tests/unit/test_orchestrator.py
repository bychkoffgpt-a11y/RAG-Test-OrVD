from src.api.schemas import AskRequest
from src.rag.orchestrator import RagOrchestrator


class _NoContextRetriever:
    def retrieve(self, question, top_k, scope):
        return []


class _NeverCalledLlm:
    def generate(self, prompt, max_tokens=512, temperature=0.1):
        raise AssertionError('LLM should not be called when contexts are empty')


def test_orchestrator_returns_fallback_when_no_contexts():
    orch = RagOrchestrator()
    orch.retriever = _NoContextRetriever()
    orch.llm = _NeverCalledLlm()

    payload = AskRequest(question='Привет', top_k=8, scope='all')
    response = orch.answer(payload)

    assert 'Не нашёл релевантных данных' in response.answer
    assert response.sources == []
    assert response.images == []


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


class _LlmWithFixedAnswer:
    def generate(self, prompt, max_tokens=512, temperature=0.1):
        return 'Тестовый ответ'


def test_orchestrator_sets_download_url_for_source():
    orch = RagOrchestrator()
    orch.retriever = _RetrieverWithOneContext()
    orch.llm = _LlmWithFixedAnswer()

    payload = AskRequest(question='Как провести отказ?', top_k=8, scope='all')
    response = orch.answer(payload)

    assert len(response.sources) == 1
    assert response.sources[0].download_url == '/sources/csv_ans_docs/DOC-123/download'
