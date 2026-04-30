import time

import httpx
from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse
from src.rag.orchestrator import RagOrchestrator
from src.rag.vision.input_adapter import adapt_image_attachments
from src.rag.vision.response_formatter import format_runtime_response

router = APIRouter(prefix='/ask', tags=['ask'])
orch = RagOrchestrator()


@router.post('', response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    started = time.perf_counter()
    try:
        try:
            normalized_payload = payload.model_copy(update={'attachments': adapt_image_attachments(ask_attachments=payload.attachments)})
            answer = orch.answer(normalized_payload, endpoint='/ask', pre_processing_sec=time.perf_counter() - started)
            return AskResponse.model_validate(format_runtime_response(answer, is_vision_only=True))
        except TypeError:
            normalized_payload = payload.model_copy(update={'attachments': adapt_image_attachments(ask_attachments=payload.attachments)})
            answer = orch.answer(normalized_payload)
            return AskResponse.model_validate(format_runtime_response(answer, is_vision_only=True))
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail='Таймаут запроса к LLM backend') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f'Ошибка LLM backend: {exc}') from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Ошибка обработки вопроса: {exc}') from exc
