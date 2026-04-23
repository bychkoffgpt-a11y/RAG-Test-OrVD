import logging
import time

from src.api.schemas import AskRequest, AskResponse, SourceItem
from src.core.settings import settings
from src.llm.client import LlmClient
from src.rag.answer_formatter import collect_images
from src.rag.prompt_builder import build_prompt
from src.rag.retriever import Retriever
from src.telemetry.metrics import observe_rag_stage_latency
from src.vision.service import VisionService


logger = logging.getLogger(__name__)


def _build_download_url(source_type: str, doc_id: str) -> str:
    return f'/sources/{source_type}/{doc_id}/download'


class RagOrchestrator:
    def __init__(self) -> None:
        self.retriever = Retriever()
        self.llm = LlmClient()
        self.vision = VisionService()

    def _observe_stage(
        self,
        *,
        endpoint: str,
        stage: str,
        duration_sec: float,
        payload: AskRequest,
    ) -> None:
        observe_rag_stage_latency(
            endpoint=endpoint,
            stage=stage,
            has_attachments=bool(payload.attachments),
            scope=payload.scope,
            vision_mode=settings.vision_runtime_mode,
            duration_sec=duration_sec,
        )

    def answer(
        self,
        payload: AskRequest,
        max_tokens: int = 512,
        temperature: float = 0.1,
        endpoint: str = '/ask',
        pre_processing_sec: float = 0.0,
    ) -> AskResponse:
        started = time.perf_counter()

        self._observe_stage(
            endpoint=endpoint,
            stage='pre_processing',
            duration_sec=max(pre_processing_sec, 0.0),
            payload=payload,
        )

        vision_started = time.perf_counter()
        raw_visual = []
        if payload.attachments:
            raw_visual = self.vision.analyze_attachments(payload.attachments, payload.question)
        visual_evidence = [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in raw_visual]
        vision_duration = time.perf_counter() - vision_started
        self._observe_stage(endpoint=endpoint, stage='vision', duration_sec=vision_duration, payload=payload)
        logger.info(
            'rag_vision_finished',
            extra={
                'endpoint': endpoint,
                'vision_runtime_mode': settings.vision_runtime_mode,
                'visual_evidence': len(visual_evidence),
                'attachments': len(payload.attachments),
                'skipped': not bool(payload.attachments),
                'duration_sec': round(vision_duration, 3),
            },
        )

        retrieve_started = time.perf_counter()
        contexts = self.retriever.retrieve(payload.question, payload.top_k, payload.scope)
        retrieve_duration = time.perf_counter() - retrieve_started
        self._observe_stage(endpoint=endpoint, stage='retrieval', duration_sec=retrieve_duration, payload=payload)
        logger.info(
            'rag_retrieve_finished',
            extra={
                'endpoint': endpoint,
                'contexts': len(contexts),
                'duration_sec': round(retrieve_duration, 3),
            },
        )

        if not contexts and not visual_evidence:
            logger.info('rag_no_relevant_context', extra={'endpoint': endpoint})
            total_duration = time.perf_counter() - started
            self._observe_stage(endpoint=endpoint, stage='total', duration_sec=total_duration, payload=payload)
            return AskResponse(
                answer='Не нашёл релевантных данных в базе документов по этому вопросу. Уточните запрос или выберите вопрос по документации.',
                sources=[],
                images=[],
                visual_evidence=[],
            )

        prompt_started = time.perf_counter()
        prompt = build_prompt(payload.question, contexts, visual_evidence=visual_evidence)
        prompt_duration = time.perf_counter() - prompt_started
        self._observe_stage(endpoint=endpoint, stage='prompt_build', duration_sec=prompt_duration, payload=payload)
        logger.info(
            'rag_prompt_built',
            extra={
                'endpoint': endpoint,
                'prompt_length_chars': len(prompt),
                'duration_sec': round(prompt_duration, 3),
            },
        )

        llm_started = time.perf_counter()
        answer = self.llm.generate(prompt, max_tokens=max_tokens, temperature=temperature)
        llm_duration = time.perf_counter() - llm_started
        self._observe_stage(endpoint=endpoint, stage='llm_generation', duration_sec=llm_duration, payload=payload)
        logger.info(
            'rag_llm_finished',
            extra={'endpoint': endpoint, 'duration_sec': round(llm_duration, 3)},
        )

        postprocess_started = time.perf_counter()
        sources = [
            SourceItem(
                doc_id=item['doc_id'],
                source_type=item['source_type'],
                page_number=item.get('page_number'),
                chunk_id=item['chunk_id'],
                score=item['score'],
                image_paths=item.get('image_paths', []),
                download_url=_build_download_url(item['source_type'], item['doc_id']),
            )
            for item in contexts
        ]
        images = collect_images(contexts)
        postprocess_duration = time.perf_counter() - postprocess_started
        self._observe_stage(endpoint=endpoint, stage='post_formatting', duration_sec=postprocess_duration, payload=payload)

        total_duration = time.perf_counter() - started
        self._observe_stage(endpoint=endpoint, stage='total', duration_sec=total_duration, payload=payload)

        logger.info(
            'rag_answer_ready',
            extra={
                'endpoint': endpoint,
                'sources': len(sources),
                'images': len(images),
                'visual_evidence': len(visual_evidence),
                'duration_sec': round(total_duration, 3),
            },
        )
        logger.info(
            'rag_pipeline_profile',
            extra={
                'endpoint': endpoint,
                'scope': payload.scope,
                'has_attachments': bool(payload.attachments),
                'vision_runtime_mode': settings.vision_runtime_mode,
                'stage_pre_processing_sec': round(max(pre_processing_sec, 0.0), 3),
                'stage_vision_sec': round(vision_duration, 3),
                'stage_retrieval_sec': round(retrieve_duration, 3),
                'stage_prompt_build_sec': round(prompt_duration, 3),
                'stage_llm_generation_sec': round(llm_duration, 3),
                'stage_post_formatting_sec': round(postprocess_duration, 3),
                'stage_total_sec': round(total_duration, 3),
            },
        )

        return AskResponse(answer=answer, sources=sources, images=images, visual_evidence=visual_evidence)
