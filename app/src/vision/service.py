import logging
import os
import re
import time
from pathlib import Path
from typing import Iterable

from src.api.schemas import AttachmentItem, VisionEvidenceItem
from src.core.settings import settings

logger = logging.getLogger(__name__)


class VisionService:
    _ocr_client = None

    @staticmethod
    def _resolve_ocr_use_gpu() -> bool:
        preferred = settings.vision_ocr_device.strip().lower()
        if preferred not in {'auto', 'cpu', 'cuda'}:
            raise ValueError(f'Unsupported vision OCR device: {settings.vision_ocr_device}')

        if preferred == 'cpu':
            return False

        try:
            import paddle
        except Exception:
            if preferred == 'cuda':
                raise RuntimeError('CUDA device requested for OCR, but paddle is unavailable')
            return False

        has_cuda = bool(getattr(paddle, 'is_compiled_with_cuda', lambda: False)())
        if preferred == 'cuda':
            if not has_cuda:
                raise RuntimeError('CUDA device requested for OCR, but paddle CUDA runtime is unavailable')
            return True
        return has_cuda

    def analyze_attachments(self, attachments: Iterable[AttachmentItem], question: str) -> list[VisionEvidenceItem]:
        if not settings.vision_enabled:
            logger.info('vision_disabled')
            return []

        started = time.perf_counter()
        items = list(attachments)
        logger.info('vision_request_received', extra={'images': len(items), 'question_length': len(question)})

        evidence: list[VisionEvidenceItem] = []
        for attachment in items:
            image_path = attachment.image_path.strip()
            if not image_path:
                continue
            evidence.append(self._analyze_single_image(image_path))

        logger.info(
            'vision_request_finished',
            extra={'images': len(evidence), 'duration_sec': round(time.perf_counter() - started, 3)},
        )
        return evidence

    def build_document_image_chunks(self, image_assets: Iterable[dict], *, doc_id: str, source_type: str) -> list[dict]:
        if not settings.vision_ingest_enabled:
            logger.warning(
                'vision_ingest_disabled',
                extra={'doc_id': doc_id, 'source_type': source_type},
            )
            return []

        chunks: list[dict] = []
        for idx, item in enumerate(image_assets):
            image_path = str(item.get('path', '')).strip()
            if not image_path:
                continue
            ocr_text = self._run_ocr(image_path)
            summary = self._build_summary(image_path, ocr_text)
            text = f"[IMAGE] {summary}\nOCR:\n{ocr_text}".strip()
            if len(text) < 20:
                continue

            chunks.append(
                {
                    'chunk_id': f'{doc_id}_img_{idx}',
                    'text': text,
                    'page_number': item.get('page_number'),
                    'image_paths': [image_path],
                    'source_type': source_type,
                    'doc_id': doc_id,
                }
            )
        return chunks

    def _analyze_single_image(self, image_path: str) -> VisionEvidenceItem:
        started = time.perf_counter()
        ocr_text = self._run_ocr(image_path)
        summary = self._build_summary(image_path, ocr_text)
        confidence = self._estimate_confidence(ocr_text)

        logger.info(
            'vision_image_processed',
            extra={
                'image_path': image_path,
                'ocr_text_length': len(ocr_text),
                'confidence': confidence,
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )

        return VisionEvidenceItem(
            image_path=image_path,
            ocr_text=ocr_text,
            summary=summary,
            confidence=confidence,
        )

    @classmethod
    def _get_ocr_client(cls):
        if cls._ocr_client is not None:
            return cls._ocr_client

        model_root = settings.vision_ocr_model_root
        missing = cls._missing_ocr_artifacts(model_root)
        if missing:
            logger.error(
                'vision_ocr_models_missing',
                extra={
                    'model_root': model_root,
                    'missing_files': missing,
                    'hint': 'OCR веса должны быть предзагружены офлайн; runtime-download в read-only /models невозможен',
                },
            )
            return None

        if not os.access(model_root, os.W_OK):
            logger.info(
                'vision_ocr_model_root_readonly',
                extra={'model_root': model_root},
            )

        try:
            from paddleocr import PaddleOCR

            use_gpu = cls._resolve_ocr_use_gpu()
            ocr = PaddleOCR(
                use_angle_cls=settings.vision_ocr_use_angle_cls,
                lang=settings.vision_ocr_lang,
                show_log=settings.vision_ocr_show_log,
                use_gpu=use_gpu,
                det_model_dir=os.path.join(model_root, 'det'),
                rec_model_dir=os.path.join(model_root, 'rec'),
                cls_model_dir=os.path.join(model_root, 'cls'),
            )
            cls._ocr_client = ocr
            logger.info(
                'vision_ocr_initialized',
                extra={'model_root': model_root, 'lang': settings.vision_ocr_lang, 'use_gpu': use_gpu},
            )
            return cls._ocr_client
        except ImportError as exc:
            hint = ''
            lowered = str(exc).lower()
            if 'libgl.so.1' in lowered:
                hint = (
                    'Не найдена системная библиотека libGL.so.1. '
                    'Проверьте, что в образе установлены libgl1/libglib2.0-0 '
                    'или используйте headless-сборку OpenCV.'
                )
            logger.exception('vision_ocr_init_failed_import', extra={'hint': hint})
            return None
        except Exception:
            logger.exception('vision_ocr_init_failed')
            return None

    @staticmethod
    def _missing_ocr_artifacts(model_root: str) -> list[str]:
        root = Path(model_root)
        required = {
            'det': ['inference.pdmodel', 'inference.pdiparams'],
            'rec': ['inference.pdmodel', 'inference.pdiparams'],
            'cls': ['inference.pdmodel', 'inference.pdiparams'],
        }
        missing: list[str] = []
        for subdir, files in required.items():
            base = root / subdir
            for name in files:
                path = base / name
                if not path.exists():
                    missing.append(str(path))
        return missing

    def _run_ocr(self, image_path: str) -> str:
        if not os.path.exists(image_path):
            logger.warning('vision_image_not_found', extra={'image_path': image_path})
            return ''

        ocr_client = self._get_ocr_client()
        if ocr_client is None:
            return ''

        try:
            result = ocr_client.ocr(image_path, cls=settings.vision_ocr_use_angle_cls)
            texts: list[str] = []
            for line in result or []:
                for block in line or []:
                    if isinstance(block, (list, tuple)) and len(block) > 1:
                        payload = block[1]
                        if isinstance(payload, (list, tuple)) and payload:
                            text = str(payload[0]).strip()
                            if text:
                                texts.append(text)
            if texts:
                return '\n'.join(texts)
        except Exception:
            logger.exception('vision_ocr_failed', extra={'image_path': image_path})

        return ''

    @staticmethod
    def _build_summary(image_path: str, ocr_text: str) -> str:
        lowered = ocr_text.lower()
        hints: list[str] = []

        if re.search(r'\b(error|exception|traceback|critical|failed)\b', lowered):
            hints.append('На скриншоте обнаружены признаки ошибки приложения')
        if re.search(r'\b(403|404|500|502|503|504)\b', lowered):
            hints.append('Присутствует HTTP-код ошибки')
        if 'доступ запрещен' in lowered or 'access denied' in lowered:
            hints.append('Похоже на проблему с доступом')
        if not hints:
            hints.append('Скриншот обработан, явных сигнатур критической ошибки не найдено')

        file_hint = Path(image_path).name
        return f"{'; '.join(hints)}. Файл: {file_hint}"

    @staticmethod
    def _estimate_confidence(ocr_text: str) -> float:
        if not ocr_text:
            return 0.15
        if len(ocr_text) < 20:
            return 0.45
        if len(ocr_text) < 120:
            return 0.65
        return 0.82
