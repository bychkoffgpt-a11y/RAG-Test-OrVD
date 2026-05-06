from unittest.mock import MagicMock, patch, call

import pytest
from qdrant_client.models import Distance, VectorParams, PointStruct

from src.storage.qdrant_repo import QdrantRepo


def _make_repo(mock_client: MagicMock) -> QdrantRepo:
    with patch('src.storage.qdrant_repo.QdrantClient', return_value=mock_client):
        return QdrantRepo()


def _fake_client(existing_collections: list[str] | None = None) -> MagicMock:
    client = MagicMock()
    existing = existing_collections or []
    col_mocks = []
    for name in existing:
        c = MagicMock()
        c.name = name
        col_mocks.append(c)
    client.get_collections.return_value.collections = col_mocks
    return client


def test_ensure_collection_creates_when_missing():
    client = _fake_client(existing_collections=[])
    repo = _make_repo(client)

    repo.ensure_collection('csv_ans_docs', vector_size=1024)

    client.create_collection.assert_called_once_with(
        collection_name='csv_ans_docs',
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    )


def test_ensure_collection_skips_when_exists():
    client = _fake_client(existing_collections=['csv_ans_docs'])
    repo = _make_repo(client)

    repo.ensure_collection('csv_ans_docs', vector_size=1024)

    client.create_collection.assert_not_called()


def test_ensure_collection_creates_only_missing_collection():
    client = _fake_client(existing_collections=['csv_ans_docs'])
    repo = _make_repo(client)

    repo.ensure_collection('internal_regulations', vector_size=1024)

    client.create_collection.assert_called_once()
    args = client.create_collection.call_args[1]
    assert args['collection_name'] == 'internal_regulations'


def test_upsert_points_delegates_to_client():
    client = _fake_client()
    repo = _make_repo(client)
    points = [
        PointStruct(id=1, vector=[0.1, 0.2, 0.3], payload={'doc_id': 'D1'}),
        PointStruct(id=2, vector=[0.4, 0.5, 0.6], payload={'doc_id': 'D2'}),
    ]

    repo.upsert_points('csv_ans_docs', points)

    client.upsert.assert_called_once_with(collection_name='csv_ans_docs', points=points)


def test_search_passes_correct_args_to_client():
    client = _fake_client()
    fake_hits = [MagicMock(id='1', score=0.92)]
    client.search.return_value = fake_hits
    repo = _make_repo(client)

    result = repo.search('csv_ans_docs', query_vector=[0.1, 0.2, 0.3], limit=5)

    client.search.assert_called_once_with(
        collection_name='csv_ans_docs',
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
        with_payload=True,
    )
    assert result is fake_hits


def test_search_returns_empty_list_when_no_hits():
    client = _fake_client()
    client.search.return_value = []
    repo = _make_repo(client)

    result = repo.search('csv_ans_docs', query_vector=[0.0], limit=10)

    assert result == []


def test_qdrant_client_initialized_with_settings():
    with patch('src.storage.qdrant_repo.QdrantClient') as MockClient, \
         patch('src.storage.qdrant_repo.settings') as mock_settings:
        mock_settings.qdrant_url = 'http://qdrant:6333'
        mock_settings.qdrant_timeout_sec = 30
        QdrantRepo()

    MockClient.assert_called_once_with(url='http://qdrant:6333', timeout=30)
