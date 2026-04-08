import logging
from pathlib import Path

from sentence_transformers import SentenceTransformer
from src.core.settings import settings


logger = logging.getLogger(__name__)


class EmbeddingClient:
    _model = None

    @classmethod
    def model(cls) -> SentenceTransformer:
        if cls._model is None:
            model_path = Path(settings.embedding_model_path)
            required_files = ['config.json']
            for file_name in required_files:
                if not (model_path / file_name).exists():
                    raise FileNotFoundError(
                        f'Embedding model не найден или неполный: {model_path} (нет {file_name}). '
                        'Проверьте модельные артефакты перед запуском.'
                    )

            logger.info('embedding_model_load_started', extra={'model_path': str(model_path)})
            cls._model = SentenceTransformer(str(model_path), local_files_only=True)
            logger.info('embedding_model_load_finished', extra={'model_path': str(model_path)})
        return cls._model

    @classmethod
    def embed(cls, text: str) -> list[float]:
        vector = cls.model().encode(text, normalize_embeddings=True)
        return vector.tolist()
