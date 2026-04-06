from fastapi import APIRouter
from src.api.schemas import IngestResponse
from src.ingest.pipeline_b import run_pipeline_b

router = APIRouter(prefix='/ingest/b', tags=['ingest'])


@router.post('/run', response_model=IngestResponse)
def run_ingest_b() -> IngestResponse:
    result = run_pipeline_b('/data/inbox/internal_regulations')
    return IngestResponse(**result)
