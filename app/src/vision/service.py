import logging
import os
import re
import time
from pathlib import Path
from typing import Iterable

from src.api.schemas import AttachmentItem, VisionEvidenceItem
from src.core.settings import settings

logger = logging.getLogger(__name__)
_OCR_UNSUPPORTED_IMAGE_EXTENSIONS = {'.jb2', '.jbig2'}
_VISION_MODES = {'ocr', 'vlm'}
_VLM_SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}


class VisionService:
    _ocr_client = None
    _vlm_processor = None
    _vlm_model = None
    _vlm_device = 'cpu'
    _vlm_init_failed = False

    @staticmethod
    def _build_paddle_ocr(*, model_root: str | None):
        from paddleocr import PaddleOCR

        use_gpu = VisionService._resolve_ocr_use_gpu()
        init_kwargs = {
            'use_angle_cls': settings.vision_ocr_use_angle_cls,
            'lang': settings.vision_ocr_lang,
            'show_log': settings.vision_ocr_show_log,
            'use_gpu': use_gpu,
        }
        if model_root:
            init_kwargs.update(
                {
                    'det_model_dir': os.path.join(model_root, 'det'),
                    'rec_model_dir': os.path.join(model_root, 'rec'),
                    'cls_model_dir': os.path.join(model_root, 'cls'),
                }
            )
        return PaddleOCR(**init_kwargs), use_gpu

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

        runtime_mode = self._resolve_mode(for_ingest=False)
        started = time.perf_counter()
        items = list(attachments)
        logger.info(
            'vision_request_received',
            extra={'images': len(items), 'question_length': len(question), 'mode': runtime_mode},
        )

        evidence: list[VisionEvidenceItem] = []
        for attachment in items:
            image_path = attachment.image_path.strip()
            if not image_path:
                continue
            evidence.append(self._analyze_single_image(image_path, question=question, mode=runtime_mode))

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

        ingest_mode = self._resolve_mode(for_ingest=True)
        chunks: list[dict] = []
        for idx, item in enumerate(image_assets):
            image_path = str(item.get('path', '')).strip()
            if not image_path:
                continue
            extracted_text = self._extract_image_text_or_caption(
                image_path,
                question=settings.vision_model_prompt_ingest,
                mode=ingest_mode,
            )
            summary = self._build_summary(image_path, extracted_text, mode=ingest_mode)
            body_label = 'OCR' if ingest_mode == 'ocr' else 'VLM'
            text = f"[IMAGE] {summary}\n{body_label}:\n{extracted_text}".strip()
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

    def _analyze_single_image(self, image_path: str, *, question: str, mode: str) -> VisionEvidenceItem:
        started = time.perf_counter()
        extracted_text = self._extract_image_text_or_caption(image_path, question=question, mode=mode)
        summary = self._build_summary(image_path, extracted_text, mode=mode)
        confidence = self._estimate_confidence(extracted_text)
        ocr_text = extracted_text if mode == 'ocr' else ''

        logger.info(
            'vision_image_processed',
            extra={
                'image_path': image_path,
                'extracted_text_length': len(extracted_text),
                'confidence': confidence,
                'mode': mode,
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )

        return VisionEvidenceItem(
            image_path=image_path,
            ocr_text=ocr_text,
            summary=summary,
            confidence=confidence,
        )

    @staticmethod
    def _resolve_mode(*, for_ingest: bool) -> str:
        raw_mode = settings.vision_ingest_mode if for_ingest else settings.vision_runtime_mode
        mode = str(raw_mode).strip().lower()
        if mode not in _VISION_MODES:
            logger.warning(
                'vision_mode_unsupported',
                extra={'raw_mode': raw_mode, 'allowed_modes': sorted(_VISION_MODES), 'fallback_mode': 'ocr'},
            )
            return 'ocr'
        return mode

    def _extract_image_text_or_caption(self, image_path: str, *, question: str, mode: str) -> str:
        if mode == 'vlm':
            return self._run_vlm(image_path, question=question)
        return self._run_ocr(image_path)

    @classmethod
    def _get_ocr_client(cls):
        if cls._ocr_client is not None:
            return cls._ocr_client

        model_root = settings.vision_ocr_model_root
        missing = cls._missing_ocr_artifacts(model_root)
        has_local_models = not missing
        if missing:
            logger.error(
                'vision_ocr_models_missing',
                extra={
                    'model_root': model_root,
                    'missing_files': missing,
                    'hint': (
                        'OCR веса не найдены в локальном model_root. '
                        'Будет выполнена best-effort инициализация PaddleOCR с дефолтными путями.'
                    ),
                },
            )

        if has_local_models and not os.access(model_root, os.W_OK):
            logger.info(
                'vision_ocr_model_root_readonly',
                extra={'model_root': model_root},
            )

        try:
            ocr, use_gpu = cls._build_paddle_ocr(model_root=model_root if has_local_models else None)
            cls._ocr_client = ocr
            logger.info(
                'vision_ocr_initialized',
                extra={
                    'model_root': model_root if has_local_models else 'paddle_default',
                    'lang': settings.vision_ocr_lang,
                    'use_gpu': use_gpu,
                    'has_local_models': has_local_models,
                },
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
        if Path(image_path).suffix.lower() in _OCR_UNSUPPORTED_IMAGE_EXTENSIONS:
            logger.warning('vision_ocr_skipped_unsupported_ext', extra={'image_path': image_path})
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

    @classmethod
    def _get_vlm_client(cls):
        if cls._vlm_init_failed:
            return None
        if cls._vlm_processor is not None and cls._vlm_model is not None:
            return cls._vlm_processor, cls._vlm_model, cls._vlm_device

        model_path = settings.vision_model_path
        if not Path(model_path).exists():
            logger.error('vision_vlm_model_path_missing', extra={'model_path': model_path})
            cls._vlm_init_failed = True
            return None
        try:
            import torch
            from transformers import AutoModelForVision2Seq, AutoProcessor

            processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True, local_files_only=True)
            torch_device = cls._resolve_vlm_device(torch)
            torch_dtype = cls._resolve_vlm_dtype(torch)

            model = AutoModelForVision2Seq.from_pretrained(
                model_path,
                trust_remote_code=True,
                local_files_only=True,
                torch_dtype=torch_dtype,
                device_map='auto' if torch_device == 'cuda' else None,
            )
            if torch_device == 'cpu':
                model = model.to('cpu')
            model.eval()

            cls._vlm_processor = processor
            cls._vlm_model = model
            cls._vlm_device = torch_device
            cls._vlm_init_failed = False
            logger.info(
                'vision_vlm_initialized',
                extra={'model_path': model_path, 'device': torch_device, 'dtype': settings.vision_model_dtype},
            )
            return cls._vlm_processor, cls._vlm_model, cls._vlm_device
        except Exception:
            logger.exception('vision_vlm_init_failed', extra={'model_path': model_path})
            cls._vlm_init_failed = True
            return None

    @staticmethod
    def _resolve_vlm_device(torch_module) -> str:
        preferred = settings.vision_model_device.strip().lower()
        if preferred not in {'auto', 'cpu', 'cuda'}:
            logger.warning('vision_vlm_invalid_device', extra={'value': settings.vision_model_device, 'fallback': 'auto'})
            preferred = 'auto'
        if preferred == 'cpu':
            return 'cpu'
        if preferred == 'cuda':
            if not torch_module.cuda.is_available():
                raise RuntimeError('VISION_MODEL_DEVICE=cuda, но CUDA недоступна')
            return 'cuda'
        return 'cuda' if torch_module.cuda.is_available() else 'cpu'

    @staticmethod
    def _resolve_vlm_dtype(torch_module):
        preferred = settings.vision_model_dtype.strip().lower()
        if preferred == 'float32':
            return torch_module.float32
        if preferred == 'float16':
            return torch_module.float16
        if preferred == 'bfloat16':
            return torch_module.bfloat16
        return torch_module.float16 if torch_module.cuda.is_available() else torch_module.float32

    def _run_vlm(self, image_path: str, *, question: str) -> str:
        if not os.path.exists(image_path):
            logger.warning('vision_image_not_found', extra={'image_path': image_path})
            return ''

        suffix = Path(image_path).suffix.lower()
        if suffix not in _VLM_SUPPORTED_IMAGE_EXTENSIONS:
            logger.warning(
                'vision_vlm_skipped_unsupported_ext',
                extra={'image_path': image_path, 'supported': sorted(_VLM_SUPPORTED_IMAGE_EXTENSIONS)},
            )
            return ''

        client = self._get_vlm_client()
        if client is None:
            return ''

        processor, model, device = client
        prompt = question.strip() or settings.vision_model_prompt_runtime

        try:
            import torch
            from PIL import Image

            image = Image.open(image_path).convert('RGB')

            if hasattr(processor, 'apply_chat_template'):
                messages = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': prompt}]}]
                text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            else:
                text = prompt

            inputs = processor(text=[text], images=[image], return_tensors='pt', padding=True)
            if device == 'cuda':
                inputs = {k: (v.to('cuda') if hasattr(v, 'to') else v) for k, v in inputs.items()}
            with torch.no_grad():
                generated = model.generate(**inputs, max_new_tokens=settings.vision_model_max_new_tokens)
            output = processor.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            result = (output[0] if output else '').strip()
            if result.startswith(text):
                result = result[len(text):].strip()
            return result
        except Exception:
            logger.exception('vision_vlm_inference_failed', extra={'image_path': image_path})
            return ''

    @staticmethod
    def _build_summary(image_path: str, extracted_text: str, *, mode: str) -> str:
        lowered = extracted_text.lower()
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
        mode_hint = 'OCR' if mode == 'ocr' else 'VLM'
        return f"{'; '.join(hints)}. Метод: {mode_hint}. Файл: {file_hint}"

    @staticmethod
    def _estimate_confidence(ocr_text: str) -> float:
        if not ocr_text:
            return 0.15
        if len(ocr_text) < 20:
            return 0.45
        if len(ocr_text) < 120:
            return 0.65
        return 0.82
