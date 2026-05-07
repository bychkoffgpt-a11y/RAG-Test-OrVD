import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.schemas import AttachmentItem
from src.core.settings import settings
from src.ingest.parsers.docx_parser import parse_docx
from src.ingest.parsers.pdf_parser import parse_pdf
from src.vision.service import VisionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/ocr', tags=['ocr'])

_vision = VisionService()

_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}
_SUPPORTED_EXTENSIONS = _IMAGE_EXTENSIONS | {'.pdf', '.docx', '.doc'}


class OcrPageResult(BaseModel):
    page_number: int
    text: str
    confidence: float = 0.0


class OcrUploadResponse(BaseModel):
    filename: str
    file_type: str
    page_count: int
    full_text: str
    pages: list[OcrPageResult]


def _ocr_image_assets(image_assets: list[dict]) -> dict[int | None, str]:
    """Run OCR on a list of image assets, return mapping page_number -> text."""
    page_texts: dict[int | None, str] = {}
    for asset in image_assets:
        path = asset.get('path', '')
        page_num = asset.get('page_number')
        if not path:
            continue
        attachment = AttachmentItem(image_path=path)
        try:
            evidence = _vision.analyze_attachments(
                [attachment], 'Извлеки весь текст', forced_task_type='text'
            )
        except Exception:
            logger.exception('ocr_image_asset_failed', extra={'path': path})
            continue
        if evidence:
            text = (evidence[0].ocr_text or '').strip()
            if text:
                existing = page_texts.get(page_num, '')
                page_texts[page_num] = (existing + '\n' + text).strip() if existing else text
    return page_texts


def _cleanup_parsed_images(tmp_id: str) -> None:
    path = Path(settings.file_storage_root) / 'parsed_images' / 'ocr_upload' / tmp_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


@router.post('/upload', response_model=OcrUploadResponse)
async def ocr_upload(file: UploadFile = File(...)) -> OcrUploadResponse:
    filename = file.filename or 'upload'
    ext = Path(filename).suffix.lower()

    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f'Неподдерживаемый формат файла: {ext!r}. '
                   f'Поддерживаются: {", ".join(sorted(_SUPPORTED_EXTENSIONS))}',
        )

    tmp_id = uuid.uuid4().hex
    pages: list[OcrPageResult] = []
    file_type: str

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / f'{tmp_id}{ext}'
        content = await file.read()
        tmp_path.write_bytes(content)
        logger.info('ocr_upload_received', extra={'filename': filename, 'ext': ext, 'bytes': len(content)})

        try:
            if ext in _IMAGE_EXTENSIONS:
                file_type = 'image'
                attachment = AttachmentItem(image_path=str(tmp_path))
                evidence = _vision.analyze_attachments(
                    [attachment], 'Извлеки весь текст', forced_task_type='text'
                )
                if evidence:
                    pages = [OcrPageResult(
                        page_number=1,
                        text=(evidence[0].ocr_text or '').strip(),
                        confidence=evidence[0].confidence,
                    )]

            elif ext == '.pdf':
                file_type = 'pdf'
                result = parse_pdf(str(tmp_path), source_type='ocr_upload', doc_id=tmp_id)
                page_texts_list: list[dict] = result.get('page_texts') or []
                image_assets: list[dict] = result.get('image_assets') or []

                image_ocr = _ocr_image_assets(image_assets)

                page_map: dict[int, str] = {}
                for pt in page_texts_list:
                    pn = int(pt.get('page_number', 1))
                    page_map[pn] = (pt.get('text') or '').strip()

                for page_num_key, img_text in image_ocr.items():
                    pn = int(page_num_key) if page_num_key is not None else 1
                    existing = page_map.get(pn, '')
                    page_map[pn] = (existing + '\n' + img_text).strip() if existing else img_text

                for pn in sorted(page_map):
                    pages.append(OcrPageResult(page_number=pn, text=page_map[pn]))

            else:
                file_type = 'docx'
                actual_path = str(tmp_path)
                if ext == '.doc':
                    from src.ingest.parsers.doc_converter import convert_doc_to_docx
                    actual_path = convert_doc_to_docx(str(tmp_path))

                result = parse_docx(actual_path, source_type='ocr_upload', doc_id=tmp_id)
                body_text = (result.get('text') or '').strip()
                image_assets = result.get('image_assets') or []
                image_ocr = _ocr_image_assets(image_assets)
                image_text = '\n'.join(image_ocr.values()).strip()

                combined = '\n\n'.join(t for t in [body_text, image_text] if t)
                if combined:
                    pages = [OcrPageResult(page_number=1, text=combined)]

        finally:
            _cleanup_parsed_images(tmp_id)

    full_text = '\n\n'.join(p.text for p in pages if p.text)
    logger.info('ocr_upload_done', extra={'filename': filename, 'pages': len(pages), 'chars': len(full_text)})
    return OcrUploadResponse(
        filename=filename,
        file_type=file_type,
        page_count=len(pages),
        full_text=full_text,
        pages=pages,
    )
