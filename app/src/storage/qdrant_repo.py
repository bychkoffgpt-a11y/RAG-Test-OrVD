import logging
from typing import Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from src.core.settings import settings


logger = logging.getLogger(__name__)


class QdrantRepo:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url, timeout=settings.qdrant_timeout_sec)

    def ensure_collection(self, collection: str, vector_size: int = 1024) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if collection not in collections:
            self.client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert_points(self, collection: str, points: list[PointStruct]) -> None:
        self.client.upsert(collection_name=collection, points=points)

    def search(self, collection: str, query_vector: list[float], limit: int) -> list[Any]:
        logger.info(
            'qdrant_search_started',
            extra={'collection': collection, 'limit': limit},
        )
        return self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
        )
