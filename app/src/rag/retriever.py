import logging
import time

from src.embeddings.client import EmbeddingClient
from src.storage.qdrant_repo import QdrantRepo


logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self) -> None:
        self.qdrant = QdrantRepo()

    def retrieve(self, question: str, top_k: int, scope: str) -> list[dict]:
        started = time.perf_counter()
        query_vector = EmbeddingClient.embed(question)
        logger.info('retriever_embedding_ready', extra={'question_length': len(question)})
        collections = []
        if scope in ('all', 'csv_ans_docs'):
            collections.append('csv_ans_docs')
        if scope in ('all', 'internal_regulations'):
            collections.append('internal_regulations')

        results: list[dict] = []
        for collection in collections:
            collection_started = time.perf_counter()
            try:
                rows = self.qdrant.search(collection, query_vector, top_k)
            except Exception:
                logger.exception('retriever_collection_failed', extra={'collection': collection})
                continue

            logger.info(
                'retriever_collection_finished',
                extra={
                    'collection': collection,
                    'rows': len(rows),
                    'duration_sec': round(time.perf_counter() - collection_started, 3),
                },
            )
            for row in rows:
                payload = row.payload or {}
                results.append(
                    {
                        'doc_id': payload.get('doc_id', 'unknown'),
                        'source_type': payload.get('source_type', collection),
                        'page_number': payload.get('page_number'),
                        'chunk_id': payload.get('chunk_id', str(row.id)),
                        'text': payload.get('text', ''),
                        'image_paths': payload.get('image_paths', []),
                        'score': float(row.score),
                    }
                )

        results.sort(key=lambda x: x['score'], reverse=True)
        logger.info(
            'retriever_finished',
            extra={
                'scope': scope,
                'total_results': len(results),
                'returned_results': min(len(results), top_k),
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )
        return results[:top_k]
