from pathlib import Path
import logging

from pypdf import PdfReader

from src.core.settings import settings


logger = logging.getLogger(__name__)

_OCR_UNSUPPORTED_IMAGE_EXTENSIONS = {'jb2', 'jbig2'}


def _extract_pdf_images_with_pymupdf(
    path: str,
    *,
    output_dir: Path,
    page_number: int,
) -> tuple[list[str], list[dict]]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required to decode unsupported PDF image filters") from exc

    image_paths: list[str] = []
    image_assets: list[dict] = []

    with fitz.open(path) as doc:
        page = doc.load_page(page_number - 1)
        for image_idx, image_info in enumerate(page.get_images(full=True), start=1):
            xref = image_info[0]
            extracted = doc.extract_image(xref)
            image_ext = str(extracted.get("ext", "png")).lower()

            if image_ext in _OCR_UNSUPPORTED_IMAGE_EXTENSIONS:
                logger.warning(
                    'pymupdf extracted %s image on page %s, rendering page raster for OCR compatibility',
                    image_ext,
                    page_number,
                )
                image_name = f"page_{page_number}_{image_idx}.png"
                target = output_dir / image_name
                page.get_pixmap(alpha=False).save(target)
            else:
                image_bytes = extracted["image"]
                image_name = f"page_{page_number}_{image_idx}.{image_ext}"
                target = output_dir / image_name
                target.write_bytes(image_bytes)

            path_str = str(target)
            image_paths.append(path_str)
            image_assets.append({'path': path_str, 'page_number': page_number})

    return image_paths, image_assets


def _extract_pdf_images(reader: PdfReader, *, output_dir: Path, source_path: str) -> tuple[list[str], list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    image_assets: list[dict] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        page_images = getattr(page, 'images', []) or []
        image_idx = 0
        image_iter = iter(page_images)
        while True:
            try:
                image = next(image_iter)
            except StopIteration:
                break
            except NotImplementedError as exc:
                logger.warning(
                    "pypdf cannot decode image filter on page %s (%s), using PyMuPDF fallback",
                    page_idx,
                    exc,
                )
                fallback_paths, fallback_assets = _extract_pdf_images_with_pymupdf(
                    source_path,
                    output_dir=output_dir,
                    page_number=page_idx,
                )
                image_paths.extend(fallback_paths)
                image_assets.extend(fallback_assets)
                break

            image_idx += 1
            image_name = getattr(image, 'name', f'page_{page_idx}_{image_idx}.png')
            target = output_dir / image_name
            target.write_bytes(image.data)
            path_str = str(target)
            image_paths.append(path_str)
            image_assets.append({'path': path_str, 'page_number': page_idx})

    return image_paths, image_assets


def parse_pdf(path: str, *, source_type: str = 'unknown', doc_id: str | None = None) -> dict:
    reader = PdfReader(path)
    pages_text: list[str] = []
    page_texts: list[dict] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ''
        pages_text.append(page_text)
        page_texts.append({'page_number': page_idx, 'text': page_text})

    root = Path(settings.file_storage_root) / 'parsed_images' / source_type / (doc_id or Path(path).stem)
    image_paths, image_assets = _extract_pdf_images(reader, output_dir=root, source_path=path)

    return {
        'pages': len(reader.pages),
        'text': '\n'.join(pages_text),
        'page_texts': page_texts,
        'images': image_paths,
        'image_assets': image_assets,
    }
