from pydantic import BaseModel, Field
from typing import List
from typing import Literal, Optional


class AttachmentItem(BaseModel):
    image_path: str = Field(..., min_length=1)
    page_number: int | None = None
    source_url: str | None = None


class VisionEvidenceItem(BaseModel):
    image_path: str
    source_url: str | None = None
    ocr_text: str = ''
    summary: str = ''
    confidence: float = 0.0
    task_type: str = 'text'
    visible_facts: list[str] = Field(default_factory=list)
    display_text: str = ''
    vlm_output_format: Literal['json', 'raw'] | None = None
    vlm_diagnostics: dict[str, str] | None = None
    vlm_json_parse_ok: bool | None = None
    vlm_raw_length: int | None = None
    vlm_fallback_applied: bool | None = None
    vlm_max_new_tokens_used: int | None = None


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


class VisionDebugRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    attachments: List[AttachmentItem] = Field(..., min_length=1)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    task_type: Optional[str] = None


class VisionDebugResponse(BaseModel):
    answer: str
    visual_evidence: List[VisionEvidenceItem] = Field(default_factory=list)
    chart_mode: bool = False


class IngestResponse(BaseModel):
    source_type: str
    processed_files: int
    created_points: int
    diagnostics: dict[str, int] | None = None
    message: str
