from src.ingest.chunking import chunk_text


def test_chunk_text_non_empty():
    text = 'a' * 2500
    chunks = chunk_text(text, chunk_size=900, overlap=120)
    assert len(chunks) >= 3
