from pydantic import BaseModel, Field
from typing import List


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = 8
    scope: str = Field(default='all', description='all|csv_ans_docs|internal_regulations')


class SourceItem(BaseModel):
    doc_id: str
    source_type: str
    page_number: int | None = None
    chunk_id: str
    score: float
    image_paths: List[str] = []
    download_url: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    images: List[str]


class IngestResponse(BaseModel):
    source_type: str
    processed_files: int
    created_points: int
    message: str
