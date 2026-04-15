import logging
import hashlib
from pathlib import Path

from qdrant_client.models import PointStruct

from src.embeddings.client import EmbeddingClient
from src.ingest.chunking import chunk_text
from src.ingest.dedup_hash import file_sha256
from src.ingest.parsers.doc_converter import convert_doc_to_docx
from src.ingest.parsers.docx_parser import parse_docx
from src.ingest.parsers.pdf_parser import parse_pdf
from src.storage.postgres_repo import PostgresRepo
from src.storage.qdrant_repo import QdrantRepo
from src.vision.service import VisionService

logger = logging.getLogger(__name__)


def _stable_point_id(source_type: str, chunk_id: str) -> int:
    """
    Детерминированный идентификатор точки для Qdrant.

    Нельзя использовать встроенный hash(), т.к. он рандомизируется между
    процессами Python и приводит к разным id на повторных ingestion-запусках.
    """
    digest = hashlib.sha256(f'{source_type}:{chunk_id}'.encode('utf-8')).digest()
    return int.from_bytes(digest[:8], byteorder='big', signed=False)


def _extract_structured_metadata(chunk_text: str, strategy: str) -> dict:
    first_sentence = chunk_text.split('. ')[0][:180]
    metadata = {
        'section_title': first_sentence,
        'clause_ref': None,
    }
    if strategy == 'regs':
        metadata['clause_ref'] = first_sentence
    return metadata


def _parse_file(path: Path, source_type: str) -> dict:
    suffix = path.suffix.lower()
    doc_id = path.stem
    if suffix == '.docx':
        return parse_docx(str(path), source_type=source_type, doc_id=doc_id)
    if suffix == '.pdf':
        return parse_pdf(str(path), source_type=source_type, doc_id=doc_id)
    if suffix == '.doc':
        converted = convert_doc_to_docx(str(path))
        return parse_docx(converted, source_type=source_type, doc_id=doc_id)
    raise ValueError(f'Неподдерживаемый формат: {suffix}')




def _build_text_chunks_with_pages(parsed: dict, *, chunk_size: int, overlap: int, chunk_strategy: str) -> list[tuple[str, int | None]]:
    page_texts = parsed.get('page_texts') or []
    if page_texts:
        chunks_with_pages: list[tuple[str, int | None]] = []
        for page_item in page_texts:
            page_number = page_item.get('page_number')
            page_chunks = chunk_text(
                page_item.get('text', ''),
                chunk_size=chunk_size,
                overlap=overlap,
                strategy=chunk_strategy,
            )
            chunks_with_pages.extend((chunk, page_number) for chunk in page_chunks)
        return chunks_with_pages

    text_chunks = chunk_text(
        parsed.get('text', ''),
        chunk_size=chunk_size,
        overlap=overlap,
        strategy=chunk_strategy,
    )
    return [(chunk, None) for chunk in text_chunks]

def _build_image_points(vision: VisionService, parsed: dict, *, doc_id: str, source_type: str) -> list[dict]:
    image_assets = parsed.get('image_assets') or []
    return vision.build_document_image_chunks(image_assets, doc_id=doc_id, source_type=source_type)


def run_pipeline(
    input_dir: str,
    source_type: str,
    *,
    chunk_size: int = 900,
    overlap: int = 120,
    chunk_strategy: str = 'fixed',
) -> dict:
    qdrant = QdrantRepo()
    postgres = PostgresRepo()
    vision = VisionService()
    qdrant.ensure_collection(source_type, vector_size=1024)

    folder = Path(input_dir)
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.doc', '.docx', '.pdf'}]

    processed_files = 0
    created_points = 0

    for file_path in files:
        parsed = _parse_file(file_path, source_type)
        doc_id = file_path.stem
        file_hash = file_sha256(str(file_path))

        postgres.save_document(
            {
                'doc_id': doc_id,
                'source_type': source_type,
                'file_name': file_path.name,
                'file_hash': file_hash,
                'pages': parsed.get('pages'),
            }
        )

        text_chunks_with_pages = _build_text_chunks_with_pages(
            parsed,
            chunk_size=chunk_size,
            overlap=overlap,
            chunk_strategy=chunk_strategy,
        )
        image_points = _build_image_points(vision, parsed, doc_id=doc_id, source_type=source_type)
        image_assets_count = len(parsed.get('image_assets') or [])
        logger.info(
            'ingest_image_assets_processed',
            extra={
                'doc_id': doc_id,
                'source_type': source_type,
                'image_assets_count': image_assets_count,
                'image_points_count': len(image_points),
            },
        )
        if image_assets_count > 0 and not image_points:
            logger.warning(
                'ingest_image_chunks_empty_after_extraction',
                extra={'doc_id': doc_id, 'source_type': source_type, 'image_assets_count': image_assets_count},
            )
        points = []

        for idx, (ch, page_number) in enumerate(text_chunks_with_pages):
            chunk_id = f'{doc_id}_ch_{idx}'
            vector = EmbeddingClient.embed(ch)
            structured_metadata = _extract_structured_metadata(ch, chunk_strategy)
            payload = {
                'doc_id': doc_id,
                'source_type': source_type,
                'chunk_id': chunk_id,
                'text': ch,
                'page_number': page_number,
                'image_paths': parsed.get('images', []),
                'section_title': structured_metadata['section_title'],
                'clause_ref': structured_metadata['clause_ref'],
                'modality': 'text',
            }
            points.append(PointStruct(id=_stable_point_id(source_type, chunk_id), vector=vector, payload=payload))

            postgres.save_chunk(
                {
                    'doc_id': doc_id,
                    'source_type': source_type,
                    'chunk_id': chunk_id,
                    'page_number': page_number,
                    'text_preview': ch,
                    'image_paths': parsed.get('images', []),
                }
            )

        for image_item in image_points:
            vector = EmbeddingClient.embed(image_item['text'])
            payload = {
                'doc_id': doc_id,
                'source_type': source_type,
                'chunk_id': image_item['chunk_id'],
                'text': image_item['text'],
                'page_number': image_item.get('page_number'),
                'image_paths': image_item.get('image_paths', []),
                'section_title': 'IMAGE_EVIDENCE',
                'clause_ref': None,
                'modality': 'image_ocr',
            }
            points.append(
                PointStruct(
                    id=_stable_point_id(source_type, image_item['chunk_id']),
                    vector=vector,
                    payload=payload,
                )
            )
            postgres.save_chunk(
                {
                    'doc_id': doc_id,
                    'source_type': source_type,
                    'chunk_id': image_item['chunk_id'],
                    'page_number': image_item.get('page_number'),
                    'text_preview': image_item['text'],
                    'image_paths': image_item.get('image_paths', []),
                }
            )

        if points:
            qdrant.upsert_points(source_type, points)
            created_points += len(points)
        processed_files += 1
        logger.info('Файл обработан: %s (%s чанков)', file_path.name, len(points))

    return {
        'source_type': source_type,
        'processed_files': processed_files,
        'created_points': created_points,
        'message': f'Индексация {source_type} завершена',
    }
