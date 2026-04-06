from sentence_transformers import SentenceTransformer
from src.core.settings import settings


class EmbeddingClient:
    _model = None

    @classmethod
    def model(cls) -> SentenceTransformer:
        if cls._model is None:
            cls._model = SentenceTransformer(settings.embedding_model_path)
        return cls._model

    @classmethod
    def embed(cls, text: str) -> list[float]:
        vector = cls.model().encode(text, normalize_embeddings=True)
        return vector.tolist()
