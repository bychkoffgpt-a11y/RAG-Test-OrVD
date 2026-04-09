from pathlib import Path

from pypdf import PdfReader

from src.core.settings import settings


def _extract_pdf_images(reader: PdfReader, *, output_dir: Path) -> tuple[list[str], list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    image_assets: list[dict] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        page_images = getattr(page, 'images', []) or []
        for image_idx, image in enumerate(page_images, start=1):
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
    for page in reader.pages:
        pages_text.append(page.extract_text() or '')

    root = Path(settings.file_storage_root) / 'parsed_images' / source_type / (doc_id or Path(path).stem)
    image_paths, image_assets = _extract_pdf_images(reader, output_dir=root)

    return {
        'pages': len(reader.pages),
        'text': '\n'.join(pages_text),
        'images': image_paths,
        'image_assets': image_assets,
    }
