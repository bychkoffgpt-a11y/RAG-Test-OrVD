from types import SimpleNamespace

from src.rag.retriever import Retriever


class _FakeQdrant:
    def search(self, collection, query_vector, limit):
        assert query_vector == [0.1, 0.2, 0.3]
        assert limit == 3
        if collection == "csv_ans_docs":
            return [
                SimpleNamespace(
                    id="1",
                    score=0.4,
                    payload={
                        "doc_id": "DOC-1",
                        "source_type": "csv_ans_docs",
                        "page_number": 10,
                        "chunk_id": "chunk-1",
                        "text": "A",
                        "image_paths": ["x.png"],
                    },
                )
            ]
        return [
            SimpleNamespace(
                id="2",
                score=0.9,
                payload={
                    "doc_id": "REG-2",
                    "source_type": "internal_regulations",
                    "page_number": 5,
                    "chunk_id": "chunk-2",
                    "text": "B",
                    "image_paths": ["y.png"],
                },
            )
        ]


class _FakeQdrantWithDuplicates:
    def search(self, collection, query_vector, limit):
        assert query_vector == [0.1, 0.2, 0.3]
        assert limit == 8
        if collection == "csv_ans_docs":
            return [
                SimpleNamespace(
                    id="1",
                    score=0.91,
                    payload={
                        "doc_id": "vision_regression_marker",
                        "source_type": "csv_ans_docs",
                        "page_number": 1,
                        "chunk_id": "vision_regression_marker_ch_0",
                        "text": "ERR-9A7K-UNIQUE",
                        "image_paths": ["m1.png"],
                    },
                ),
                SimpleNamespace(
                    id="99",
                    score=0.90,
                    payload={
                        "doc_id": "vision_regression_marker",
                        "source_type": "csv_ans_docs",
                        "page_number": 1,
                        "chunk_id": "vision_regression_marker_ch_0",
                        "text": "ERR-9A7K-UNIQUE",
                        "image_paths": ["m1.png"],
                    },
                ),
            ]
        return []


def test_retrieve_merges_reranks_sorts_and_limits(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])
    monkeypatch.setattr("src.rag.retriever.RerankerClient.rerank", lambda q, docs: [0.2, 0.8])
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_candidate_pool_multiplier", 1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_min_score", 0.1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_use_reranker", True)

    retriever = Retriever()
    retriever.qdrant = _FakeQdrant()

    result = retriever.retrieve("test", top_k=3, scope="all")

    assert len(result) == 2
    assert result[0]["doc_id"] == "REG-2"
    assert result[0]["rerank_score"] == 0.8
    assert result[1]["doc_id"] == "DOC-1"


def test_retrieve_handles_collection_error(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])
    monkeypatch.setattr("src.rag.retriever.RerankerClient.rerank", lambda q, docs: [0.8])
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_candidate_pool_multiplier", 1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_min_score", 0.1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_use_reranker", True)

    class _PartiallyFailingQdrant(_FakeQdrant):
        def search(self, collection, query_vector, limit):
            if collection == "csv_ans_docs":
                raise RuntimeError("boom")
            return super().search(collection, query_vector, limit)

    retriever = Retriever()
    retriever.qdrant = _PartiallyFailingQdrant()

    result = retriever.retrieve("test", top_k=3, scope="all")

    assert len(result) == 1
    assert result[0]["source_type"] == "internal_regulations"


def test_retrieve_filters_low_relevance(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])
    monkeypatch.setattr("src.rag.retriever.RerankerClient.rerank", lambda q, docs: [0.05, 0.08])
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_candidate_pool_multiplier", 1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_min_score", 0.1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_use_reranker", True)

    retriever = Retriever()
    retriever.qdrant = _FakeQdrant()

    result = retriever.retrieve("test", top_k=3, scope="all")

    assert result == []


def test_retrieve_deduplicates_same_chunk(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_candidate_pool_multiplier", 1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_min_score", 0.1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_use_reranker", False)

    retriever = Retriever()
    retriever.qdrant = _FakeQdrantWithDuplicates()

    result = retriever.retrieve("marker", top_k=8, scope="all")

    assert len(result) == 1
    assert result[0]["doc_id"] == "vision_regression_marker"
    assert result[0]["chunk_id"] == "vision_regression_marker_ch_0"


def test_retrieve_with_trace_includes_raw_and_rerank(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])
    monkeypatch.setattr("src.rag.retriever.RerankerClient.rerank", lambda q, docs: [0.2, 0.8])
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_candidate_pool_multiplier", 1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_min_score", 0.1)
    monkeypatch.setattr("src.rag.retriever.settings.retrieval_use_reranker", True)

    retriever = Retriever()
    retriever.qdrant = _FakeQdrant()

    contexts, trace = retriever.retrieve_with_trace("test", top_k=3, scope="all")

    assert len(contexts) == 2
    assert "csv_ans_docs" in trace["raw_by_collection"]
    assert "internal_regulations" in trace["raw_by_collection"]
    assert trace["combined_sorted"][0]["doc_id"] == "REG-2"
    assert trace["reranker"]["applied"] is True
    assert set(trace["timings_sec"]) == {"embedding", "retrieval", "rerank", "total"}
