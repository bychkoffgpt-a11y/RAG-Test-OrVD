import logging
import time

from src.api.schemas import AskRequest, AskResponse, SourceItem
from src.llm.client import LlmClient
from src.rag.answer_formatter import collect_images
from src.rag.prompt_builder import build_prompt
from src.rag.retriever import Retriever


logger = logging.getLogger(__name__)


class RagOrchestrator:
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.llm = LlmClient()

    def answer(self, payload: AskRequest, max_tokens: int = 512, temperature: float = 0.1) -> AskResponse:
        started = time.perf_counter()

        retrieve_started = time.perf_counter()
        contexts = self.retriever.retrieve(payload.question, payload.top_k, payload.scope)
        logger.info(
            'rag_retrieve_finished',
            extra={
                'contexts': len(contexts),
                'duration_sec': round(time.perf_counter() - retrieve_started, 3),
            },
        )

        if not contexts:
            logger.info('rag_no_relevant_context')
            return AskResponse(
                answer='Не нашёл релевантных данных в базе документов по этому вопросу. Уточните запрос или выберите вопрос по документации.',
                sources=[],
                images=[],
            )

        prompt_started = time.perf_counter()
        prompt = build_prompt(payload.question, contexts)
        logger.info(
            'rag_prompt_built',
            extra={
                'prompt_length_chars': len(prompt),
                'duration_sec': round(time.perf_counter() - prompt_started, 3),
            },
        )

        llm_started = time.perf_counter()
        answer = self.llm.generate(prompt, max_tokens=max_tokens, temperature=temperature)
        logger.info(
            'rag_llm_finished',
            extra={'duration_sec': round(time.perf_counter() - llm_started, 3)},
        )

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

        logger.info(
            'rag_answer_ready',
            extra={
                'sources': len(sources),
                'images': len(images),
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )

        return AskResponse(answer=answer, sources=sources, images=images)
