import time

import httpx
from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse
from src.core.request_context import get_request_id
from src.rag.orchestrator import RagOrchestrator
from src.rag.vision.input_adapter import AttachmentNormalizationError, adapt_image_attachments, build_image_debug_info
from src.rag.vision.response_formatter import format_runtime_response

router = APIRouter(prefix='/ask', tags=['ask'])
orch = RagOrchestrator()


@router.post('', response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    started = time.perf_counter()
    try:
        try:
            normalized_payload = payload.model_copy(update={'attachments': adapt_image_attachments(ask_attachments=payload.attachments)})
            expected_debug = build_image_debug_info(
                normalized_payload.attachments, trace_id=get_request_id(), endpoint='/ask', stage='endpoint_input'
            )
            answer = orch.answer(
                normalized_payload, endpoint='/ask', pre_processing_sec=time.perf_counter() - started, expected_image_debug=expected_debug
            )
            return AskResponse.model_validate(format_runtime_response(answer, is_vision_only=True))
        except TypeError:
            normalized_payload = payload.model_copy(update={'attachments': adapt_image_attachments(ask_attachments=payload.attachments)})
            answer = orch.answer(normalized_payload)
            return AskResponse.model_validate(format_runtime_response(answer, is_vision_only=True))
    except AttachmentNormalizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail='Таймаут запроса к LLM backend') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f'Ошибка LLM backend: {exc}') from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Ошибка обработки вопроса: {exc}') from exc
