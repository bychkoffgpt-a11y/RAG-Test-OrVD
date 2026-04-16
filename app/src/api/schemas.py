from pydantic import BaseModel, Field
from typing import List


class AttachmentItem(BaseModel):
    image_path: str = Field(..., min_length=1)
    page_number: int | None = None


class VisionEvidenceItem(BaseModel):
    image_path: str
    ocr_text: str = ''
    summary: str = ''
    confidence: float = 0.0


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: int = 8
    scope: str = Field(default='all', description='all|csv_ans_docs|internal_regulations')
    attachments: List[AttachmentItem] = Field(default_factory=list)


class SourceItem(BaseModel):
    doc_id: str
    source_type: str
    page_number: int | None = None
    chunk_id: str
    score: float
    image_paths: List[str] = Field(default_factory=list)
    download_url: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    images: List[str]
    visual_evidence: List[VisionEvidenceItem] = Field(default_factory=list)


class IngestResponse(BaseModel):
    source_type: str
    processed_files: int
    created_points: int
    diagnostics: dict[str, int] | None = None
    message: str
