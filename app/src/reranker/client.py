import logging
from pathlib import Path

from sentence_transformers import CrossEncoder

from src.core.settings import settings


logger = logging.getLogger(__name__)


class RerankerClient:
    _model = None

    @staticmethod
    def _resolve_device(preferred: str) -> str:
        normalized = preferred.strip().lower()
        if normalized not in {'auto', 'cpu', 'cuda'}:
            raise ValueError(f'Unsupported reranker device: {preferred}')

        if normalized == 'cpu':
            return 'cpu'

        try:
            import torch
        except Exception:
            if normalized == 'cuda':
                raise RuntimeError('CUDA device requested for reranker, but torch is unavailable')
            return 'cpu'

        if normalized == 'cuda':
            if not torch.cuda.is_available():
                raise RuntimeError('CUDA device requested for reranker, but no CUDA device is available')
            return 'cuda'

        return 'cuda' if torch.cuda.is_available() else 'cpu'

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

            device = cls._resolve_device(settings.reranker_device)
            logger.info('reranker_model_load_started', extra={'model_path': str(model_path), 'device': device})
            cls._model = CrossEncoder(str(model_path), local_files_only=True, device=device)
            logger.info('reranker_model_load_finished', extra={'model_path': str(model_path), 'device': device})
        return cls._model

    @classmethod
    def rerank(cls, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        pairs = [[query, doc] for doc in documents]
        scores = cls.model().predict(pairs, show_progress_bar=False)
        return [float(score) for score in scores]
