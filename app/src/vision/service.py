import json
import logging
import os
import re
import threading
import time
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from src.api.schemas import AttachmentItem, VisionEvidenceItem
from pydantic import BaseModel, Field, ValidationError
from src.core.settings import settings

logger = logging.getLogger(__name__)
_OCR_UNSUPPORTED_IMAGE_EXTENSIONS = {'.jb2', '.jbig2'}
_VISION_MODES = {'ocr', 'vlm'}
_VLM_SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}
_VISION_TASK_TYPES = {'text', 'sign', 'chart'}
_VLM_RAW_FALLBACK_MAX_CHARS = 2000
_FACT_WHITELIST_KEYS = {'id', 'due', 'date', 'room', 'owner', 'status', 'capacity'}


class VlmChartPoint(BaseModel):
    label: str = ''
    value: str = ''


class VlmStructuredResponse(BaseModel):
    visible_facts: list[str] = Field(default_factory=list)
    uncertain_facts: list[str] = Field(default_factory=list)
    not_visible: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @staticmethod
    def _normalize_fact(value: str) -> str:
        return re.sub(r'\s+', ' ', (value or '').strip().lower())

    def model_post_init(self, __context) -> None:
        normalized_visible = {self._normalize_fact(item) for item in self.visible_facts if item.strip()}
        normalized_uncertain = {self._normalize_fact(item) for item in self.uncertain_facts if item.strip()}
        normalized_not_visible = {self._normalize_fact(item) for item in self.not_visible if item.strip()}

        collisions = (
            (normalized_visible & normalized_uncertain)
            | (normalized_visible & normalized_not_visible)
            | (normalized_uncertain & normalized_not_visible)
        )
        if collisions:
            raise ValueError('VLM response has duplicate facts across sections')

        # Высокая уверенность не должна сопровождаться пометкой "не видно/нечитаемо".
        if self.confidence >= 0.75 and normalized_not_visible:
            raise ValueError('High-confidence VLM response cannot contain not_visible facts')



class VisionService:
    _ocr_client = None
    _vlm_processor = None
    _vlm_model = None
    _vlm_device = 'cpu'
    _vlm_init_failed = False
    _vlm_init_lock = threading.Lock()

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

    def analyze_attachments(
        self,
        attachments: Iterable[AttachmentItem],
        question: str,
        *,
        forced_task_type: str | None = None,
    ) -> list[VisionEvidenceItem]:
        if not settings.vision_enabled:
            logger.info('vision_disabled')
            return []

        runtime_mode = self._resolve_mode(for_ingest=False)
        started = time.perf_counter()
        items = self._apply_runtime_limits(list(attachments))
        timeout_sec = max(float(settings.vision_runtime_timeout_sec), 0.0)
        deadline = started + timeout_sec if timeout_sec > 0 else None
        logger.info(
            'vision_request_received',
            extra={
                'images': len(items),
                'question_length': len(question),
                'mode': runtime_mode,
                'timeout_sec': timeout_sec,
            },
        )

        evidence: list[VisionEvidenceItem] = []
        for attachment in items:
            if deadline is not None and time.perf_counter() >= deadline:
                logger.warning(
                    'vision_request_timeout',
                    extra={
                        'timeout_sec': timeout_sec,
                        'processed_images': len(evidence),
                        'requested_images': len(items),
                    },
                )
                break
            image_path = attachment.image_path.strip()
            if not image_path:
                continue
            evidence.append(
                self._analyze_single_image(
                    image_path,
                    source_url=attachment.source_url,
                    question=question,
                    mode=runtime_mode,
                    deadline=deadline,
                    forced_task_type=forced_task_type,
                )
            )

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
                deadline=None,
                allow_raw_fallback=False,
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

    def _analyze_single_image(
        self,
        image_path: str,
        *,
        source_url: str | None,
        question: str,
        mode: str,
        deadline: float | None,
        forced_task_type: str | None = None,
    ) -> VisionEvidenceItem:
        started = time.perf_counter()
        pixels_limit = int(settings.vision_runtime_max_image_pixels)
        if pixels_limit > 0 and self._image_exceeds_pixels_limit(image_path, max_pixels=pixels_limit):
            logger.warning(
                'vision_image_skipped_too_large',
                extra={
                    'image_path': image_path,
                    'max_pixels': pixels_limit,
                },
            )
            return VisionEvidenceItem(
                image_path=image_path,
                source_url=source_url,
                ocr_text='',
                summary=(
                    f'Изображение пропущено: превышен лимит VISION_RUNTIME_MAX_IMAGE_PIXELS={pixels_limit}. '
                    'Уменьшите изображение или увеличьте лимит.'
                ),
                confidence=0.0,
            )

        task_type = (forced_task_type or "").strip() or self._detect_task_type(question=question, image_path=image_path)
        effective_image_path = image_path
        cleanup_path: str | None = None
        if mode == 'vlm' and task_type == 'chart':
            effective_image_path, cleanup_path = self._prepare_chart_image_for_vlm(image_path)
        extracted_text = self._extract_image_text_or_caption(
            effective_image_path,
            question=self._build_task_instruction(question=question, task_type=task_type),
            mode=mode,
            deadline=deadline,
            allow_raw_fallback=True,
        )
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                logger.debug('vision_chart_temp_cleanup_failed', extra={'image_path': cleanup_path})
        summary = self._build_summary(image_path, extracted_text, mode=mode)
        confidence = self._estimate_confidence(extracted_text)
        vlm_output_format: str | None = None
        if mode == 'ocr':
            ocr_text = extracted_text
        else:
            ocr_text = self._compose_structured_text(extracted_text, task_type=task_type)
            if extracted_text.strip():
                vlm_output_format = 'json' if self._parse_vlm_json(extracted_text) is not None else 'raw'
            if not ocr_text and vlm_output_format == 'raw':
                ocr_text = extracted_text.strip()
            if not ocr_text.strip():
                ocr_text = self._sanitize_vlm_fallback_text(extracted_text)

        logger.info(
            'vision_image_processed',
            extra={
                'image_path': image_path,
                'extracted_text_length': len(extracted_text),
                'confidence': confidence,
                'mode': mode,
                'task_type': task_type,
                'duration_sec': round(time.perf_counter() - started, 3),
            },
        )

        return VisionEvidenceItem(
            image_path=image_path,
            source_url=source_url,
            ocr_text=ocr_text,
            summary=summary,
            confidence=confidence,
            task_type=task_type,
            vlm_output_format=vlm_output_format,
        )

    @staticmethod
    def _prepare_chart_image_for_vlm(image_path: str) -> tuple[str, str | None]:
        max_w = max(int(settings.vision_chart_downscale_max_width), 0)
        max_h = max(int(settings.vision_chart_downscale_max_height), 0)
        if max_w <= 0 or max_h <= 0:
            return image_path, None
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
                if width <= max_w and height <= max_h:
                    return image_path, None
                ratio = min(max_w / float(width), max_h / float(height))
                target_size = (max(int(width * ratio), 1), max(int(height * ratio), 1))
                resized = img.convert('RGB').resize(target_size, Image.Resampling.LANCZOS)
                with tempfile.NamedTemporaryFile(prefix='chart_ds_', suffix='.jpg', delete=False) as tmp:
                    resized.save(tmp.name, format='JPEG', quality=92, optimize=True)
                    logger.info(
                        'vision_chart_image_downscaled',
                        extra={'image_path': image_path, 'from': f'{width}x{height}', 'to': f'{target_size[0]}x{target_size[1]}'},
                    )
                    return tmp.name, tmp.name
        except Exception:
            logger.warning('vision_chart_image_downscale_failed', extra={'image_path': image_path}, exc_info=True)
            return image_path, None

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

    def _extract_image_text_or_caption(
        self,
        image_path: str,
        *,
        question: str,
        mode: str,
        deadline: float | None = None,
        allow_raw_fallback: bool = False,
    ) -> str:
        if mode == 'vlm':
            return self._run_vlm(
                image_path,
                question=question,
                deadline=deadline,
                allow_raw_fallback=allow_raw_fallback,
            )
        return self._run_ocr(image_path)

    @staticmethod
    def _detect_task_type(*, question: str, image_path: str = '') -> str:
        signal = f'{question} {Path(image_path).name}'.lower()
        if any(k in signal for k in ('chart', 'graph', 'plot', 'diagram', 'диаграм', 'график', 'legend', 'axis', 'ось')):
            return 'chart'
        if any(k in signal for k in ('sign', 'plate', 'notice', 'warning', 'знак', 'таблич', 'указател', 'предупрежден')):
            return 'sign'
        return 'text'

    @staticmethod
    def _build_task_instruction(*, question: str, task_type: str) -> str:
        if task_type == 'chart':
            return (
                f'{question}\n'
                'Режим chart: извлеки легенду, оси, ключевые точки/тренды; '
                'неуверенность помечай явно.'
            )
        if task_type == 'sign':
            return (
                f'{question}\n'
                'Режим sign: коротко извлеки только видимый текст знака/таблички. '
                'Строго запрещено домысливать отсутствующие детали.'
            )
        return (
            f'{question}\n'
            'Режим text: максимальная OCR-точность, построчное извлечение и пары ключ-значение.'
        )

    @staticmethod
    def _apply_runtime_limits(items: list[AttachmentItem]) -> list[AttachmentItem]:
        max_images = int(settings.vision_runtime_max_images)
        if max_images > 0 and len(items) > max_images:
            logger.warning(
                'vision_runtime_max_images_exceeded',
                extra={'requested_images': len(items), 'max_images': max_images},
            )
            return items[:max_images]
        return items

    @staticmethod
    def _image_exceeds_pixels_limit(image_path: str, *, max_pixels: int) -> bool:
        if max_pixels <= 0 or not Path(image_path).exists():
            return False
        try:
            from PIL import Image

            with Image.open(image_path) as image:
                width, height = image.size
            return (width * height) > max_pixels
        except Exception:
            logger.exception('vision_image_size_check_failed', extra={'image_path': image_path})
            return False

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

        with cls._vlm_init_lock:
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

    @classmethod
    def preload_runtime_models(cls) -> None:
        if not settings.vision_enabled or not settings.vision_runtime_preload:
            return
        runtime_mode = cls._resolve_mode(for_ingest=False)
        started = time.perf_counter()
        logger.info('vision_runtime_preload_started', extra={'mode': runtime_mode})
        if runtime_mode == 'vlm':
            cls._get_vlm_client()
        else:
            cls._get_ocr_client()
        logger.info(
            'vision_runtime_preload_finished',
            extra={'mode': runtime_mode, 'duration_sec': round(time.perf_counter() - started, 3)},
        )

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

    def _run_vlm(
        self,
        image_path: str,
        *,
        question: str,
        deadline: float | None,
        allow_raw_fallback: bool = False,
    ) -> str:
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
            prompt_len = int(inputs['input_ids'].shape[1])
            if device == 'cuda':
                inputs = {k: (v.to('cuda') if hasattr(v, 'to') else v) for k, v in inputs.items()}
            generate_kwargs = {'max_new_tokens': settings.vision_model_max_new_tokens}
            if deadline is not None:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    logger.warning('vision_vlm_timeout_before_generate', extra={'image_path': image_path})
                    return ''
                generate_kwargs['max_time'] = remaining
            with torch.no_grad():
                generated = model.generate(**inputs, **generate_kwargs)
            result = self._decode_generated_tail(processor, generated, prompt_len=prompt_len)
            if self._parse_vlm_json(result) is not None:
                return result

            repair_text = self._repair_prompt(result)
            if hasattr(processor, 'apply_chat_template'):
                repair_messages = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': repair_text}]}]
                repair_prompt = processor.apply_chat_template(repair_messages, tokenize=False, add_generation_prompt=True)
            else:
                repair_prompt = repair_text
            repair_inputs = processor(text=[repair_prompt], images=[image], return_tensors='pt', padding=True)
            repair_prompt_len = int(repair_inputs['input_ids'].shape[1])
            if device == 'cuda':
                repair_inputs = {k: (v.to('cuda') if hasattr(v, 'to') else v) for k, v in repair_inputs.items()}
            with torch.no_grad():
                repair_generated = model.generate(**repair_inputs, **generate_kwargs)
            repaired = self._decode_generated_tail(processor, repair_generated, prompt_len=repair_prompt_len)
            if self._parse_vlm_json(repaired) is None:
                logger.warning('vision_vlm_json_invalid_after_retry', extra={'image_path': image_path})
                if allow_raw_fallback:
                    fallback = self._sanitize_vlm_fallback_text(repaired or result)
                    logger.info(
                        'vision_vlm_raw_fallback_used',
                        extra={'image_path': image_path, 'fallback_length': len(fallback)},
                    )
                    return fallback
                return ''
            return repaired
        except Exception:
            logger.exception('vision_vlm_inference_failed', extra={'image_path': image_path})
            return ''

    @staticmethod
    def _decode_generated_tail(processor, generated, *, prompt_len: int) -> str:
        decoded = processor.batch_decode(
            generated[:, prompt_len:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )
        return (decoded[0] if decoded else '').strip()

    @staticmethod
    def _sanitize_vlm_fallback_text(raw_output: str) -> str:
        fallback = (raw_output or '').strip()
        if not fallback:
            return '[vlm_empty_output]'
        if len(fallback) > _VLM_RAW_FALLBACK_MAX_CHARS:
            return fallback[:_VLM_RAW_FALLBACK_MAX_CHARS]
        return fallback

    @staticmethod
    def _repair_prompt(raw_output: str) -> str:
        return (
            'Исправь ответ. Верни только валидный JSON строго по схеме '
            '(visible_facts, uncertain_facts, not_visible, confidence). '
            'Не дублируй один и тот же факт в разных секциях. '
            'Если confidence >= 0.75, массив not_visible должен быть пустым. '
            f'Текущий невалидный ответ: {raw_output}'
        )

    @staticmethod
    def _normalize_for_scoring(text: str) -> str:
        normalized = unicodedata.normalize('NFKC', (text or '').strip().lower())
        normalized = re.sub(r'[\u2012\u2013\u2014\u2212]', '-', normalized)
        normalized = re.sub(r'(?<=\d)[\s,](?=\d{3}\b)', '', normalized)
        normalized = re.sub(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', r'\3-\2-\1', normalized)
        normalized = re.sub(r'\b(kg|kgs|кг\.?|килограмм(?:ов|а)?)\b', 'kg', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip()

    def _compose_structured_text(self, raw_output: str, *, task_type: str = 'text') -> str:
        parsed = self._parse_vlm_json(raw_output)
        if task_type == 'chart':
            chart_text = self._compose_chart_canonical_text(parsed=parsed, raw_output=raw_output)
            if chart_text:
                return chart_text
        if parsed is None:
            return ''

        facts = [*parsed.visible_facts, *parsed.uncertain_facts, *parsed.not_visible]
        atomic_lines = self._collect_atomic_fact_lines(facts)
        if atomic_lines:
            return self._normalize_for_scoring(' | '.join(atomic_lines))
        return self._normalize_for_scoring(' | '.join(facts))

    def _compose_chart_canonical_text(self, *, parsed: VlmStructuredResponse | None, raw_output: str) -> str:
        facts = [*parsed.visible_facts, *parsed.uncertain_facts, *parsed.not_visible] if parsed else [raw_output]
        blob = self._normalize_for_scoring(' | '.join(facts))
        if not blob:
            return ''

        chart_type = 'не определен'
        if any(k in blob for k in ('pie', 'круг', 'donut')):
            chart_type = 'круговая'
        elif any(k in blob for k in ('line', 'линей')):
            chart_type = 'линейная'
        elif any(k in blob for k in ('bar', 'column', 'столб', 'гистограмм')):
            chart_type = 'столбчатая'

        categories: list[str] = []
        for pattern in (r'\bq[1-4]\b', r'\b(?:jan|feb|mar|apr|may)\b', r'\b(?:chrome|safari|firefox|edge)\b'):
            for item in re.findall(pattern, blob, flags=re.IGNORECASE):
                normalized = item.lower()
                if normalized not in categories:
                    categories.append(normalized)

        max_match = re.search(r'(?:highest|max(?:imum)?|наибольш|максимум)[:\s-]*([a-zа-я0-9_.%-]+)', blob)
        min_match = re.search(r'(?:lowest|min(?:imum)?|наименьш|минимум)[:\s-]*([a-zа-я0-9_.%-]+)', blob)
        max_hint = max_match.group(1) if max_match else 'не определен'
        min_hint = min_match.group(1) if min_match else 'не определен'

        trend = 'не определен'
        if any(k in blob for k in ('upward', 'growing', 'increase', 'рост', 'вырос', 'ascending')):
            trend = 'рост'
        elif any(k in blob for k in ('downward', 'decline', 'decrease', 'паден', 'снижен', 'descending')):
            trend = 'снижение'
        elif any(k in blob for k in ('stable', 'flat', 'без изменений', 'ровн')):
            trend = 'стабильный'

        lines = [
            f'тип: {chart_type}',
            f"категории: {', '.join(categories) if categories else 'не определены'}",
            f'максимум: {max_hint}',
            f'минимум: {min_hint}',
            f'тренд: {trend}',
        ]
        return self._normalize_for_scoring(' | '.join(lines))

    @staticmethod
    def _collect_atomic_fact_lines(facts: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            if not isinstance(fact, str):
                continue
            segments = re.split(r'[\n;|]+', fact)
            for segment in segments:
                cleaned = re.sub(r'\s+', ' ', segment).strip(' \t\r\n-:')
                if not cleaned:
                    continue

                key_match = re.match(r'^([a-zA-Zа-яА-Я0-9_\- ]{1,40})\s*[:=]\s*(.+)$', cleaned)
                if key_match:
                    key = key_match.group(1).strip().lower()
                    value = key_match.group(2).strip()
                    if value and (key in _FACT_WHITELIST_KEYS or value):
                        cleaned = f'{key_match.group(1).strip()}: {value}'
                    else:
                        continue

                normalized = VisionService._normalize_for_scoring(cleaned)
                if not normalized or normalized in seen:
                    continue
                if len(normalized) < 2:
                    continue
                seen.add(normalized)
                result.append(cleaned)
        return result

    @staticmethod
    def _extract_fact_text(value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value).strip()
        if isinstance(value, dict):
            for key in ('fact', 'text', 'value'):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
                if isinstance(candidate, (int, float, bool)):
                    rendered = str(candidate).strip()
                    if rendered:
                        return rendered
            pairs: list[str] = []
            for key, item in value.items():
                key_str = str(key).strip()
                val_str = str(item).strip() if item is not None else ''
                if key_str and val_str:
                    pairs.append(f'{key_str}: {val_str}')
            return '; '.join(pairs).strip()
        return ''

    @staticmethod
    def _normalize_vlm_facts(values: object) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            rendered = VisionService._extract_fact_text(item)
            if rendered:
                normalized.append(rendered)
        return normalized

    @staticmethod
    def _strip_markdown_json_wrapper(raw_output: str) -> str:
        cleaned = (raw_output or '').strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```\s*json\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'^```\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_json_code_block(raw_output: str) -> str | None:
        match = re.search(r"```\s*json\s*(.*?)```", raw_output, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        content = match.group(1).strip()
        return content or None

    @staticmethod
    def _extract_first_balanced_json_object(raw_output: str) -> str | None:
        start = raw_output.find('{')
        while start != -1:
            depth = 0
            in_string = False
            escaped = False
            for idx in range(start, len(raw_output)):
                char = raw_output[idx]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == '\\':
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                    continue
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return raw_output[start: idx + 1]
            start = raw_output.find('{', start + 1)
        return None

    def _validate_vlm_json_payload(self, payload: str) -> tuple[VlmStructuredResponse | None, str]:
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return None, 'raw_not_json'
        if isinstance(data, dict):
            for field_name in ('visible_facts', 'uncertain_facts', 'not_visible'):
                data[field_name] = self._normalize_vlm_facts(data.get(field_name))

        try:
            return VlmStructuredResponse.model_validate(data), ''
        except ValidationError:
            return None, 'json_schema_invalid'

    def _parse_vlm_json(self, raw_output: str) -> VlmStructuredResponse | None:
        cleaned_output = self._strip_markdown_json_wrapper(raw_output)
        parsed, reason = self._validate_vlm_json_payload(cleaned_output)
        if parsed is not None:
            return parsed

        json_block = self._extract_json_code_block(cleaned_output)
        if json_block is not None:
            parsed, reason = self._validate_vlm_json_payload(json_block)
            if parsed is not None:
                return parsed

        json_object = self._extract_first_balanced_json_object(cleaned_output)
        if json_object is not None:
            parsed, reason = self._validate_vlm_json_payload(json_object)
            if parsed is not None:
                return parsed

        if json_block is None and json_object is None and reason == 'raw_not_json':
            reason = 'json_block_not_found'
        logger.warning('vision_vlm_json_parse_failed', extra={'reason': reason})
        return None

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
            if extracted_text.strip():
                hints.append('Скриншот обработан, обнаружены визуальные элементы')
            else:
                hints.append('Скриншот обработан, текст не распознан')

        parsed = urlparse(image_path)
        file_hint = Path(parsed.path or image_path).name
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
