import base64
import binascii
import hashlib
import logging
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.api.schemas import AttachmentItem
from src.core.settings import settings

logger = logging.getLogger(__name__)
_HASH_BYTES_LIMIT = 64 * 1024


class AttachmentNormalizationError(ValueError):
    pass


def _ensure_runtime_upload_dir() -> Path:
    target = Path(settings.file_storage_root).joinpath('runtime_uploads')
    target.mkdir(parents=True, exist_ok=True)
    return target


def _resolve_path_alias(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        return normalized
    mappings = [item.strip() for item in settings.vision_attachment_path_aliases.split(';') if item.strip()]
    for mapping in mappings:
        if '=' not in mapping:
            continue
        source_prefix, target_prefix = mapping.split('=', 1)
        source_prefix = source_prefix.strip()
        target_prefix = target_prefix.strip()
        if source_prefix and target_prefix and normalized.startswith(source_prefix):
            return normalized.replace(source_prefix, target_prefix, 1)
    return normalized


def _write_payload_to_file(payload: bytes, mime: str, raw_url: str = '') -> str:
    if len(payload) > settings.vision_attachment_max_bytes:
        logger.warning('attachment_too_large', extra={'bytes': len(payload), 'max_bytes': settings.vision_attachment_max_bytes})
        return ''
    if mime and mime not in settings.vision_attachment_allowed_mime_types:
        logger.warning('attachment_unsupported_mime', extra={'mime': mime, 'url': raw_url})
        return ''

    suffix = mimetypes.guess_extension(mime) if mime else None
    if not suffix and raw_url:
        suffix = Path(urlparse(raw_url).path).suffix
    suffix = suffix or '.png'

    file_path = _ensure_runtime_upload_dir().joinpath(f'{uuid.uuid4().hex}{suffix}')
    file_path.write_bytes(payload)
    return str(file_path)


def _materialize_data_url(raw_url: str) -> str:
    if not raw_url.startswith('data:image/') or ';base64,' not in raw_url:
        return ''
    header, payload = raw_url.split(';base64,', 1)
    mime = header[len('data:') :].strip().lower()
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        raise AttachmentNormalizationError('Invalid data:image base64 payload')
    return _write_payload_to_file(decoded, mime, raw_url)


def _materialize_remote_url(raw_url: str) -> str:
    if not raw_url.startswith(('http://', 'https://')):
        return ''
    timeout = httpx.Timeout(10.0, connect=5.0)
    try:
        response = httpx.get(raw_url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError:
        raise AttachmentNormalizationError(f'Failed to fetch remote image URL: {raw_url}')
    if response.status_code >= 400:
        raise AttachmentNormalizationError(f'Remote image URL returned HTTP {response.status_code}: {raw_url}')

    content_type = str(response.headers.get('content-type', '')).split(';', 1)[0].strip().lower()
    return _write_payload_to_file(response.content, content_type, raw_url)


def normalize_image_reference(raw_value: str) -> str:
    normalized = str(raw_value or '').strip()
    if not normalized:
        return ''
    if normalized.startswith('file://'):
        normalized = normalized[len('file://') :]

    materialized = _materialize_data_url(normalized)
    if materialized:
        return materialized

    materialized = _materialize_remote_url(normalized)
    if materialized:
        return materialized

    guessed_mime = mimetypes.guess_type(normalized)[0] or ''
    if guessed_mime and guessed_mime not in settings.vision_attachment_allowed_mime_types:
        logger.warning('attachment_local_unsupported_mime', extra={'path': normalized, 'mime': guessed_mime})
        return ''
    return _resolve_path_alias(normalized)


def adapt_image_attachments(*, ask_attachments: list | None = None, message_content: list | None = None) -> list[AttachmentItem]:
    extracted: list[AttachmentItem] = []

    if ask_attachments:
        for item in ask_attachments:
            if isinstance(item, AttachmentItem):
                extracted.append(item)
            elif isinstance(item, dict) and isinstance(item.get('image_path'), str):
                extracted.append(AttachmentItem(**item))

    if message_content:
        for part in message_content:
            if not isinstance(part, dict) or part.get('type') not in {'image_url', 'input_image', 'image'}:
                continue
            raw_url = None
            image_url = part.get('image_url')
            if isinstance(image_url, dict):
                raw_url = image_url.get('url')
            elif isinstance(image_url, str):
                raw_url = image_url
            if raw_url is None:
                raw_url = part.get('url')
            if isinstance(raw_url, str) and raw_url.strip():
                extracted.append(AttachmentItem(image_path=raw_url.strip()))

    deduped: list[AttachmentItem] = []
    seen: set[str] = set()
    for item in extracted:
        normalized_path = normalize_image_reference(item.image_path)
        if not normalized_path:
            continue
        key = normalized_path.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(AttachmentItem(image_path=normalized_path, page_number=item.page_number))

    max_images = int(settings.vision_runtime_max_images)
    if max_images > 0:
        return deduped[:max_images]
    return deduped


def build_image_debug_info(attachments: list[AttachmentItem], *, trace_id: str, endpoint: str, stage: str) -> list[dict]:
    info: list[dict] = []
    for item in attachments:
        path = str(item.image_path or '').strip()
        mime = (mimetypes.guess_type(path)[0] or '').lower()
        byte_size = 0
        digest = ''
        try:
            payload = Path(path).read_bytes()
            byte_size = len(payload)
            digest = hashlib.sha256(payload[:_HASH_BYTES_LIMIT]).hexdigest()
        except OSError:
            digest = ''
        info.append(
            {
                'image_path': path,
                'mime': mime,
                'byte_size': byte_size,
                'sha256_first_64kb': digest,
            }
        )
    logger.info(
        'image_adapter_debug',
        extra={
            'trace_id': trace_id,
            'endpoint': endpoint,
            'stage': stage,
            'image_count': len(info),
            'images': info,
        },
    )
    return info
