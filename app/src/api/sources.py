from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.core.settings import settings
from src.storage.postgres_repo import PostgresRepo

router = APIRouter(prefix='/sources', tags=['sources'])
postgres = PostgresRepo()


@router.get('/health')
def sources_health() -> dict:
    return {'status': 'ok'}


@router.get('/{source_type}/{doc_id}/exists')
def source_document_exists(source_type: str, doc_id: str) -> dict:
    """
    Диагностический endpoint для регрессионных проверок:
    показывает, что документ и чанки действительно сохранены после ingest.
    """
    return {
        'source_type': source_type,
        'doc_id': doc_id,
        'document_exists': postgres.document_exists(source_type, doc_id),
        'chunk_count': postgres.chunk_count_for_document(source_type, doc_id),
    }


@router.get('/{source_type}/{doc_id}/download')
def download_source_document(source_type: str, doc_id: str):
    file_name = postgres.get_document_file_name(source_type, doc_id)
    if not file_name:
        raise HTTPException(status_code=404, detail='Документ не найден')

    base_dir = Path(settings.file_storage_root) / 'inbox' / source_type
    candidate = (base_dir / file_name).resolve()
    base_resolved = base_dir.resolve()

    if base_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail='Некорректный путь к документу')
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail='Файл документа не найден на диске')

    return FileResponse(path=candidate, filename=file_name)
