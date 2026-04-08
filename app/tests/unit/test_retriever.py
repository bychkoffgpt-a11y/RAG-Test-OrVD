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


def test_retrieve_merges_sorts_and_limits(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])

    retriever = Retriever()
    retriever.qdrant = _FakeQdrant()

    result = retriever.retrieve("test", top_k=3, scope="all")

    assert len(result) == 2
    assert result[0]["doc_id"] == "REG-2"
    assert result[1]["doc_id"] == "DOC-1"


def test_retrieve_handles_collection_error(monkeypatch):
    monkeypatch.setattr("src.rag.retriever.EmbeddingClient.embed", lambda question: [0.1, 0.2, 0.3])

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
