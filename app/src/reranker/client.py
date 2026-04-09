import logging
from pathlib import Path

from sentence_transformers import CrossEncoder

from src.core.settings import settings


logger = logging.getLogger(__name__)


class RerankerClient:
    _model = None

    @classmethod
    def model(cls) -> CrossEncoder:
        if cls._model is None:
            model_path = Path(settings.reranker_model_path)
            required_files = ['config.json']
            for file_name in required_files:
                if not (model_path / file_name).exists():
                    raise FileNotFoundError(
                        f'Reranker model не найден или неполный: {model_path} (нет {file_name}). '
                        'Проверьте модельные артефакты перед запуском.'
                    )

            logger.info('reranker_model_load_started', extra={'model_path': str(model_path)})
            cls._model = CrossEncoder(str(model_path), local_files_only=True)
            logger.info('reranker_model_load_finished', extra={'model_path': str(model_path)})
        return cls._model

    @classmethod
    def rerank(cls, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        pairs = [[query, doc] for doc in documents]
        scores = cls.model().predict(pairs)
        return [float(score) for score in scores]
