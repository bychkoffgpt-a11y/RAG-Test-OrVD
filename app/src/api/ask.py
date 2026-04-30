import time

import httpx
from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse
from src.rag.orchestrator import RagOrchestrator

router = APIRouter(prefix='/ask', tags=['ask'])
orch = RagOrchestrator()


@router.post('', response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    started = time.perf_counter()
    try:
        try:
            return orch.answer(payload, endpoint='/ask', pre_processing_sec=time.perf_counter() - started)
        except TypeError:
            return orch.answer(payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail='Таймаут запроса к LLM backend') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f'Ошибка LLM backend: {exc}') from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Ошибка обработки вопроса: {exc}') from exc
