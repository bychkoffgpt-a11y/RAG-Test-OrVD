from src.embeddings.client import EmbeddingClient
from src.storage.qdrant_repo import QdrantRepo


class Retriever:
    def __init__(self) -> None:
        self.qdrant = QdrantRepo()

    def retrieve(self, question: str, top_k: int, scope: str) -> list[dict]:
        query_vector = EmbeddingClient.embed(question)
        collections = []
        if scope in ('all', 'csv_ans_docs'):
            collections.append('csv_ans_docs')
        if scope in ('all', 'internal_regulations'):
            collections.append('internal_regulations')

        results: list[dict] = []
        for collection in collections:
            rows = self.qdrant.search(collection, query_vector, top_k)
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
        return results[:top_k]
