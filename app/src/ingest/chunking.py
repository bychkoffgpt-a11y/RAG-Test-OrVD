def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    text = ' '.join(text.split())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
