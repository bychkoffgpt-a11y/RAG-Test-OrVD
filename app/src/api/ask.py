from fastapi import APIRouter, HTTPException
from src.api.schemas import AskRequest, AskResponse
from src.rag.orchestrator import RagOrchestrator

router = APIRouter(prefix='/ask', tags=['ask'])
orch = RagOrchestrator()


@router.post('', response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        return orch.answer(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Ошибка обработки вопроса: {exc}') from exc
