from src.api.schemas import AskRequest, AskResponse, SourceItem
from src.llm.client import LlmClient
from src.rag.answer_formatter import collect_images
from src.rag.prompt_builder import build_prompt
from src.rag.retriever import Retriever


class RagOrchestrator:
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.llm = LlmClient()

    def answer(self, payload: AskRequest) -> AskResponse:
        contexts = self.retriever.retrieve(payload.question, payload.top_k, payload.scope)
        prompt = build_prompt(payload.question, contexts)
        answer = self.llm.generate(prompt)

        sources = [
            SourceItem(
                doc_id=item['doc_id'],
                source_type=item['source_type'],
                page_number=item.get('page_number'),
                chunk_id=item['chunk_id'],
                score=item['score'],
                image_paths=item.get('image_paths', []),
            )
            for item in contexts
        ]
        images = collect_images(contexts)

        return AskResponse(answer=answer, sources=sources, images=images)
