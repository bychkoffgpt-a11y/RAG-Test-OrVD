import logging
from pathlib import Path

from sentence_transformers import SentenceTransformer
from src.core.settings import settings


logger = logging.getLogger(__name__)


class EmbeddingClient:
    _model = None
    _device = None

    @staticmethod
    def _resolve_device(preferred: str) -> str:
        normalized = preferred.strip().lower()
        if normalized not in {'auto', 'cpu', 'cuda'}:
            raise ValueError(f'Unsupported embedding device: {preferred}')

        if normalized == 'cpu':
            return 'cpu'

        try:
            import torch
        except Exception:
            if normalized == 'cuda':
                if settings.embedding_device_strict:
                    raise RuntimeError('CUDA device requested for embeddings, but torch is unavailable')
                logger.warning(
                    'embedding_cuda_unavailable_fallback_cpu',
                    extra={'reason': 'torch_unavailable', 'requested_device': normalized},
                )
            return 'cpu'

        if normalized == 'cuda':
            if not torch.cuda.is_available():
                if settings.embedding_device_strict:
                    raise RuntimeError('CUDA device requested for embeddings, but no CUDA device is available')
                logger.warning(
                    'embedding_cuda_unavailable_fallback_cpu',
                    extra={'reason': 'cuda_device_unavailable', 'requested_device': normalized},
                )
                return 'cpu'
            return 'cuda'

        return 'cuda' if torch.cuda.is_available() else 'cpu'

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

            resolved_device = cls._resolve_device(settings.embedding_device)
            cls._load_model(model_path, resolved_device)
        return cls._model

    @classmethod
    def embed(cls, text: str) -> list[float]:
        model = cls.model()
        try:
            vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        except RuntimeError as exc:
            if cls._device != 'cuda' or not cls._is_cuda_runtime_error(exc):
                raise

            model_path = Path(settings.embedding_model_path)
            logger.warning(
                'embedding_cuda_encode_failed_fallback_cpu',
                extra={'model_path': str(model_path), 'device': cls._device, 'error': str(exc)},
            )
            cls._load_model(model_path, 'cpu')
            vector = cls._model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vector.tolist()

    @classmethod
    def _load_model(cls, model_path: Path, device: str) -> None:
        logger.info('embedding_model_load_started', extra={'model_path': str(model_path), 'device': device})
        try:
            cls._model = SentenceTransformer(str(model_path), local_files_only=True, device=device)
            cls._device = device
            logger.info('embedding_model_load_finished', extra={'model_path': str(model_path), 'device': device})
        except RuntimeError as exc:
            if device != 'cuda' or not cls._is_cuda_runtime_error(exc):
                raise

            logger.warning(
                'embedding_cuda_load_failed_fallback_cpu',
                extra={'model_path': str(model_path), 'device': device, 'error': str(exc)},
            )
            cls._model = SentenceTransformer(str(model_path), local_files_only=True, device='cpu')
            cls._device = 'cpu'
            logger.info('embedding_model_load_finished', extra={'model_path': str(model_path), 'device': 'cpu'})

    @staticmethod
    def _is_cuda_runtime_error(error: RuntimeError) -> bool:
        message = str(error).lower()
        cuda_markers = (
            'cuda error',
            'no kernel image is available for execution on the device',
            'device-side assert',
            'invalid device function',
        )
        return any(marker in message for marker in cuda_markers)
