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
