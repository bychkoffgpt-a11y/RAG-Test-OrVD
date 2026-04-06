import json
from psycopg import connect
from src.core.settings import settings


class PostgresRepo:
    def __init__(self) -> None:
        self.dsn = settings.postgres_dsn

    def save_document(self, payload: dict) -> None:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (doc_id, source_type, file_name, file_hash, pages)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    payload['doc_id'],
                    payload['source_type'],
                    payload['file_name'],
                    payload['file_hash'],
                    payload.get('pages'),
                ),
            )
            conn.commit()

    def save_chunk(self, payload: dict) -> None:
        with connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks (doc_id, source_type, chunk_id, page_number, text_preview, image_paths)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    payload['doc_id'],
                    payload['source_type'],
                    payload['chunk_id'],
                    payload.get('page_number'),
                    payload.get('text_preview', '')[:500],
                    json.dumps(payload.get('image_paths', []), ensure_ascii=False),
                ),
            )
            conn.commit()
