from fastapi import APIRouter
from src.api.schemas import IngestResponse
from src.ingest.pipeline_a import run_pipeline_a

router = APIRouter(prefix='/ingest/a', tags=['ingest'])


@router.post('/run', response_model=IngestResponse)
def run_ingest_a() -> IngestResponse:
    result = run_pipeline_a('/data/inbox/csv_ans_docs')
    return IngestResponse(**result)
