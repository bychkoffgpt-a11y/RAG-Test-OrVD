from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.parsers.docx_parser import _extract_docx_images, parse_docx


# ---------------------------------------------------------------------------
# Helpers for building mock Document objects
# ---------------------------------------------------------------------------

def _make_mock_doc(paragraphs: list[str], rels: list[tuple] | None = None) -> MagicMock:
    """
    paragraphs: list of paragraph texts
    rels: list of (reltype_str, image_name, image_bytes) tuples
    """
    doc = MagicMock()

    para_mocks = []
    for text in paragraphs:
        p = MagicMock()
        p.text = text
        para_mocks.append(p)
    doc.paragraphs = para_mocks

    rel_dict: dict[str, MagicMock] = {}
    for i, (reltype, image_name, image_bytes) in enumerate(rels or []):
        rel = MagicMock()
        rel.reltype = reltype
        target = MagicMock()
        target.partname = f'/word/media/{image_name}'
        target.blob = image_bytes
        rel.target_part = target
        rel_dict[f'rId{i}'] = rel
    doc.part.rels = rel_dict

    return doc


# ---------------------------------------------------------------------------
# _extract_docx_images
# ---------------------------------------------------------------------------

def test_extract_docx_images_writes_image_bytes_to_disk(tmp_path):
    image_bytes = b'\x89PNG\r\n\x1a\nfake-png-data'
    doc = _make_mock_doc(
        paragraphs=[],
        rels=[('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'image1.png', image_bytes)],
    )

    paths, assets = _extract_docx_images(doc, output_dir=tmp_path)

    assert len(paths) == 1
    assert len(assets) == 1
    written = Path(paths[0])
    assert written.exists()
    assert written.read_bytes() == image_bytes
    assert assets[0]['page_number'] is None


def test_extract_docx_images_deduplicates_by_image_name(tmp_path):
    image_bytes = b'img'
    doc = _make_mock_doc(
        paragraphs=[],
        rels=[
            ('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'image1.png', image_bytes),
            ('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'image1.png', image_bytes),
        ],
    )

    paths, assets = _extract_docx_images(doc, output_dir=tmp_path)

    assert len(paths) == 1


def test_extract_docx_images_skips_non_image_relationships(tmp_path):
    doc = _make_mock_doc(
        paragraphs=[],
        rels=[
            ('http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', 'link.html', b''),
            ('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'photo.png', b'img-data'),
        ],
    )

    paths, assets = _extract_docx_images(doc, output_dir=tmp_path)

    assert len(paths) == 1
    assert 'photo.png' in paths[0]


def test_extract_docx_images_skips_rels_without_target_part(tmp_path):
    rel = MagicMock()
    rel.reltype = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
    rel.target_part = None

    doc = MagicMock()
    doc.paragraphs = []
    doc.part.rels = {'rId0': rel}

    paths, assets = _extract_docx_images(doc, output_dir=tmp_path)

    assert paths == []
    assert assets == []


def test_extract_docx_images_returns_empty_for_no_rels(tmp_path):
    doc = _make_mock_doc(paragraphs=[], rels=[])

    paths, assets = _extract_docx_images(doc, output_dir=tmp_path)

    assert paths == []
    assert assets == []


# ---------------------------------------------------------------------------
# parse_docx
# ---------------------------------------------------------------------------

def test_parse_docx_extracts_paragraph_text(tmp_path, monkeypatch):
    monkeypatch.setattr('src.ingest.parsers.docx_parser.settings.file_storage_root', str(tmp_path))

    docx_file = tmp_path / 'test.docx'
    docx_file.write_bytes(b'fake')

    mock_doc = _make_mock_doc(
        paragraphs=['Первый абзац', 'Второй абзац', ''],
        rels=[],
    )

    with patch('src.ingest.parsers.docx_parser.Document', return_value=mock_doc):
        result = parse_docx(str(docx_file), source_type='csv_ans_docs', doc_id='test-doc')

    assert 'Первый абзац' in result['text']
    assert 'Второй абзац' in result['text']


def test_parse_docx_skips_empty_paragraphs(tmp_path, monkeypatch):
    monkeypatch.setattr('src.ingest.parsers.docx_parser.settings.file_storage_root', str(tmp_path))

    docx_file = tmp_path / 'test.docx'
    docx_file.write_bytes(b'fake')

    mock_doc = _make_mock_doc(
        paragraphs=['', '   ', 'Только этот'],
        rels=[],
    )

    with patch('src.ingest.parsers.docx_parser.Document', return_value=mock_doc):
        result = parse_docx(str(docx_file), source_type='csv_ans_docs', doc_id='test-doc')

    assert result['text'] == 'Только этот'


def test_parse_docx_pages_is_always_none(tmp_path, monkeypatch):
    monkeypatch.setattr('src.ingest.parsers.docx_parser.settings.file_storage_root', str(tmp_path))

    docx_file = tmp_path / 'test.docx'
    docx_file.write_bytes(b'fake')

    mock_doc = _make_mock_doc(paragraphs=['text'], rels=[])

    with patch('src.ingest.parsers.docx_parser.Document', return_value=mock_doc):
        result = parse_docx(str(docx_file), source_type='csv_ans_docs', doc_id='test-doc')

    assert result['pages'] is None


def test_parse_docx_extracts_images_and_returns_paths(tmp_path, monkeypatch):
    monkeypatch.setattr('src.ingest.parsers.docx_parser.settings.file_storage_root', str(tmp_path))

    docx_file = tmp_path / 'test.docx'
    docx_file.write_bytes(b'fake')

    mock_doc = _make_mock_doc(
        paragraphs=['текст'],
        rels=[
            ('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'fig1.png', b'PNG'),
        ],
    )

    with patch('src.ingest.parsers.docx_parser.Document', return_value=mock_doc):
        result = parse_docx(str(docx_file), source_type='csv_ans_docs', doc_id='test-doc')

    assert len(result['images']) == 1
    assert len(result['image_assets']) == 1
    assert 'fig1.png' in result['images'][0]
