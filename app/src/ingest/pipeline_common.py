import logging
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

logger = logging.getLogger(__name__)


def _extract_structured_metadata(chunk_text: str, strategy: str) -> dict:
    first_sentence = chunk_text.split('. ')[0][:180]
    metadata = {
        'section_title': first_sentence,
        'clause_ref': None,
    }
    if strategy == 'regs':
        metadata['clause_ref'] = first_sentence
    return metadata


def _parse_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == '.docx':
        return parse_docx(str(path))
    if suffix == '.pdf':
        return parse_pdf(str(path))
    if suffix == '.doc':
        converted = convert_doc_to_docx(str(path))
        return parse_docx(converted)
    raise ValueError(f'Неподдерживаемый формат: {suffix}')


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
    qdrant.ensure_collection(source_type, vector_size=1024)

    folder = Path(input_dir)
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.doc', '.docx', '.pdf'}]

    processed_files = 0
    created_points = 0

    for file_path in files:
        parsed = _parse_file(file_path)
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

        chunks = chunk_text(
            parsed.get('text', ''),
            chunk_size=chunk_size,
            overlap=overlap,
            strategy=chunk_strategy,
        )
        points = []

        for idx, ch in enumerate(chunks):
            chunk_id = f'{doc_id}_ch_{idx}'
            vector = EmbeddingClient.embed(ch)
            structured_metadata = _extract_structured_metadata(ch, chunk_strategy)
            payload = {
                'doc_id': doc_id,
                'source_type': source_type,
                'chunk_id': chunk_id,
                'text': ch,
                'page_number': None,
                'image_paths': parsed.get('images', []),
                'section_title': structured_metadata['section_title'],
                'clause_ref': structured_metadata['clause_ref'],
            }
            points.append(PointStruct(id=abs(hash((source_type, chunk_id))) % 10**12, vector=vector, payload=payload))

            postgres.save_chunk(
                {
                    'doc_id': doc_id,
                    'source_type': source_type,
                    'chunk_id': chunk_id,
                    'page_number': None,
                    'text_preview': ch,
                    'image_paths': parsed.get('images', []),
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
