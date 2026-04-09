from pathlib import Path

from docx import Document

from src.core.settings import settings


def _extract_docx_images(doc: Document, *, output_dir: Path) -> tuple[list[str], list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    image_assets: list[dict] = []
    seen: set[str] = set()

    for rel in doc.part.rels.values():
        rel_type = str(rel.reltype)
        if 'image' not in rel_type:
            continue

        target_part = getattr(rel, 'target_part', None)
        if target_part is None:
            continue

        partname = str(getattr(target_part, 'partname', 'image.bin'))
        image_name = Path(partname).name
        if image_name in seen:
            continue
        seen.add(image_name)

        target = output_dir / image_name
        target.write_bytes(target_part.blob)
        path_str = str(target)

        image_paths.append(path_str)
        image_assets.append({'path': path_str, 'page_number': None})

    return image_paths, image_assets


def parse_docx(path: str, *, source_type: str = 'unknown', doc_id: str | None = None) -> dict:
    doc = Document(path)
    lines = [p.text for p in doc.paragraphs if p.text and p.text.strip()]

    root = Path(settings.file_storage_root) / 'parsed_images' / source_type / (doc_id or Path(path).stem)
    image_paths, image_assets = _extract_docx_images(doc, output_dir=root)

    return {
        'pages': None,
        'text': '\n'.join(lines),
        'images': image_paths,
        'image_assets': image_assets,
    }
