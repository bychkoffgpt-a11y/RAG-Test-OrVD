import logging
import time

from src.core.settings import settings
from src.embeddings.client import EmbeddingClient
from src.reranker.client import RerankerClient
from src.storage.qdrant_repo import QdrantRepo


logger = logging.getLogger(__name__)


class Retriever:
    def __init__(self) -> None:
        self.qdrant = QdrantRepo()

    def retrieve(self, question: str, top_k: int, scope: str) -> list[dict]:
        contexts, _ = self.retrieve_with_trace(question, top_k, scope)
        return contexts

    def retrieve_with_trace(self, question: str, top_k: int, scope: str) -> tuple[list[dict], dict]:
        started = time.perf_counter()
        embedding_started = time.perf_counter()
        query_vector = EmbeddingClient.embed(question)
        embedding_duration = time.perf_counter() - embedding_started
        logger.info('retriever_embedding_ready', extra={'question_length': len(question)})
        collections = []
        if scope in ('all', 'csv_ans_docs'):
            collections.append('csv_ans_docs')
        if scope in ('all', 'internal_regulations'):
            collections.append('internal_regulations')

        candidate_limit = max(top_k, top_k * settings.retrieval_candidate_pool_multiplier)
        results: list[dict] = []
        raw_by_collection: dict[str, list[dict]] = {}
        retrieval_started = time.perf_counter()
        for collection in collections:
            collection_started = time.perf_counter()
            try:
                rows = self.qdrant.search(collection, query_vector, candidate_limit)
            except Exception:
                logger.exception('retriever_collection_failed', extra={'collection': collection})
                raw_by_collection[collection] = []
                continue

            logger.info(
                'retriever_collection_finished',
                extra={
                    'collection': collection,
                    'rows': len(rows),
                    'duration_sec': round(time.perf_counter() - collection_started, 3),
                },
            )
            view: list[dict] = []
            for row in rows:
                payload = row.payload or {}
                item = {
                    'doc_id': payload.get('doc_id', 'unknown'),
                    'source_type': payload.get('source_type', collection),
                    'page_number': payload.get('page_number'),
                    'chunk_id': payload.get('chunk_id', str(row.id)),
                    'text': payload.get('text', ''),
                    'image_paths': payload.get('image_paths', []),
                    'score': float(row.score),
                    'rerank_score': None,
                }
                results.append(item)
                view.append(
                    {
                        'doc_id': item['doc_id'],
                        'source_type': item['source_type'],
                        'page_number': item['page_number'],
                        'chunk_id': item['chunk_id'],
                        'score': item['score'],
                        'text_preview': item['text'][:400],
                        'image_paths': item['image_paths'],
                    }
                )
            raw_by_collection[collection] = view

        retrieval_duration = time.perf_counter() - retrieval_started

        rerank_applied = False
        rerank_started = time.perf_counter()
        if settings.retrieval_use_reranker and results:
            try:
                rerank_scores = RerankerClient.rerank(question, [item['text'] for item in results])
                for item, rerank_score in zip(results, rerank_scores):
                    item['rerank_score'] = rerank_score
                rerank_applied = True
                results.sort(key=lambda x: x['rerank_score'] if x['rerank_score'] is not None else x['score'], reverse=True)
            except Exception:
                logger.exception('retriever_rerank_failed')
                results.sort(key=lambda x: x['score'], reverse=True)
        else:
            results.sort(key=lambda x: x['score'], reverse=True)
        rerank_duration = time.perf_counter() - rerank_started

        deduped: list[dict] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for item in results:
            key = (item['source_type'], item['doc_id'], item['chunk_id'])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        filtered: list[dict] = []
        for item in deduped:
            primary_score = item['rerank_score'] if item['rerank_score'] is not None else item['score']
            if primary_score < settings.retrieval_min_score:
                continue
            filtered.append(item)

        logger.info(
            'retriever_finished',
            extra={
                'scope': scope,
                'total_results': len(results),
                'deduped_results': len(deduped),
                'filtered_results': len(filtered),
                'returned_results': min(len(filtered), top_k),
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )
        contexts = filtered[:top_k]
        trace = {
            'query': {
                'question': question,
                'scope': scope,
                'top_k': top_k,
                'candidate_limit': candidate_limit,
            },
            'timings_sec': {
                'embedding': round(embedding_duration, 6),
                'retrieval': round(retrieval_duration, 6),
                'rerank': round(rerank_duration, 6),
                'total': round(time.perf_counter() - started, 6),
            },
            'raw_by_collection': raw_by_collection,
            'combined_sorted': [
                {
                    'doc_id': item['doc_id'],
                    'source_type': item['source_type'],
                    'page_number': item.get('page_number'),
                    'chunk_id': item['chunk_id'],
                    'score': item['score'],
                    'rerank_score': item['rerank_score'],
                    'text_preview': item.get('text', '')[:400],
                    'image_paths': item.get('image_paths', []),
                }
                for item in results
            ],
            'deduped_count': len(deduped),
            'filtered_count': len(filtered),
            'returned_count': len(contexts),
            'reranker': {
                'enabled': settings.retrieval_use_reranker,
                'applied': rerank_applied,
                'min_score': settings.retrieval_min_score,
            },
            'contexts_used_for_prompt': contexts,
        }
        return contexts, trace
