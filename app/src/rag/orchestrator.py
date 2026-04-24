import logging
import time

from src.api.schemas import AskRequest, AskResponse, SourceItem
from src.core.request_context import get_request_id
from src.core.settings import settings
from src.llm.client import LlmClient
from src.rag.answer_formatter import collect_images
from src.rag.prompt_builder import build_prompt
from src.rag.retriever import Retriever
from src.rag.trace_card import TraceCardWriter
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
        self.trace_writer = TraceCardWriter()

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
        trace_card: dict = {
            'meta': {
                'request_id': get_request_id(),
                'endpoint': endpoint,
                'vision_runtime_mode': settings.vision_runtime_mode,
            },
            'input': {
                'question': payload.question,
                'top_k': payload.top_k,
                'scope': payload.scope,
                'attachments': [item.model_dump() for item in payload.attachments],
            },
            'stages': {},
            'aggregate_timings_sec': {},
        }

        self._observe_stage(
            endpoint=endpoint,
            stage='pre_processing',
            duration_sec=max(pre_processing_sec, 0.0),
            payload=payload,
        )
        trace_card['aggregate_timings_sec']['pre_processing'] = round(max(pre_processing_sec, 0.0), 6)

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
        trace_card['stages']['vision'] = {
            'vision_runtime_mode': settings.vision_runtime_mode,
            'vision_prompt': settings.vision_model_prompt_runtime,
            'visual_evidence': visual_evidence,
            'attachments': [item.model_dump() for item in payload.attachments],
        }
        trace_card['aggregate_timings_sec']['vision'] = round(vision_duration, 6)

        contexts, retrieval_trace = self.retriever.retrieve_with_trace(payload.question, payload.top_k, payload.scope)
        retrieve_duration = retrieval_trace.get('timings_sec', {}).get('total', 0.0)
        self._observe_stage(endpoint=endpoint, stage='retrieval', duration_sec=retrieve_duration, payload=payload)
        logger.info(
            'rag_retrieve_finished',
            extra={
                'endpoint': endpoint,
                'contexts': len(contexts),
                'duration_sec': round(retrieve_duration, 3),
            },
        )
        trace_card['stages']['retrieval'] = retrieval_trace
        trace_card['aggregate_timings_sec']['embedding'] = retrieval_trace.get('timings_sec', {}).get('embedding', 0.0)
        trace_card['aggregate_timings_sec']['vector_search'] = retrieval_trace.get('timings_sec', {}).get('retrieval', 0.0)
        trace_card['aggregate_timings_sec']['rerank'] = retrieval_trace.get('timings_sec', {}).get('rerank', 0.0)
        trace_card['aggregate_timings_sec']['retrieval_total'] = round(retrieve_duration, 6)

        if not contexts and not visual_evidence:
            logger.info('rag_no_relevant_context', extra={'endpoint': endpoint})
            total_duration = time.perf_counter() - started
            self._observe_stage(endpoint=endpoint, stage='total', duration_sec=total_duration, payload=payload)
            trace_card['aggregate_timings_sec']['total'] = round(total_duration, 6)
            trace_card['stages']['result'] = {'answer': 'fallback_no_context'}
            self.trace_writer.write(trace_card)
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
        trace_card['stages']['prompt'] = {'final_prompt': prompt, 'length_chars': len(prompt)}
        trace_card['aggregate_timings_sec']['prompt_build'] = round(prompt_duration, 6)

        llm_started = time.perf_counter()
        llm_trace: dict = {}
        answer = self.llm.generate(prompt, max_tokens=max_tokens, temperature=temperature, trace=llm_trace)
        llm_duration = time.perf_counter() - llm_started
        self._observe_stage(endpoint=endpoint, stage='llm_generation', duration_sec=llm_duration, payload=payload)
        logger.info(
            'rag_llm_finished',
            extra={'endpoint': endpoint, 'duration_sec': round(llm_duration, 3)},
        )
        trace_card['stages']['llm'] = llm_trace
        trace_card['aggregate_timings_sec']['llm_generation'] = round(llm_duration, 6)

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
        trace_card['aggregate_timings_sec']['post_formatting'] = round(postprocess_duration, 6)
        trace_card['aggregate_timings_sec']['total'] = round(total_duration, 6)

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
        trace_card['stages']['output'] = {
            'answer': answer,
            'sources': [item.model_dump() for item in sources],
            'images': images,
            'visual_evidence': visual_evidence,
        }
        self.trace_writer.write(trace_card)

        return AskResponse(answer=answer, sources=sources, images=images, visual_evidence=visual_evidence)
