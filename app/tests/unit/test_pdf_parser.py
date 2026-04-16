from pathlib import Path

import src.ingest.parsers.pdf_parser as pdf_parser


class _ImageStub:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.data = data


class _PageImagesFailFirst:
    def __iter__(self):
        return self

    def __next__(self):
        raise NotImplementedError("Unsupported filter /JBIG2Decode")


class _PageStub:
    def __init__(self, images):
        self.images = images


class _ReaderStub:
    def __init__(self, pages):
        self.pages = pages


def test_extract_pdf_images_uses_pymupdf_fallback_for_unsupported_filter(tmp_path, caplog, monkeypatch):
    reader = _ReaderStub([_PageStub(_PageImagesFailFirst())])
    fallback_target = tmp_path / "fallback.png"
    fallback_target.write_bytes(b"fallback")
    fallback_paths = [str(fallback_target)]
    fallback_assets = [{"path": str(fallback_target), "page_number": 1}]

    monkeypatch.setattr(
        pdf_parser,
        "_extract_pdf_images_with_pymupdf",
        lambda path, *, output_dir, page_number: (fallback_paths, fallback_assets),
    )

    with caplog.at_level("WARNING"):
        image_paths, image_assets = pdf_parser._extract_pdf_images(
            reader,
            output_dir=tmp_path,
            source_path="/tmp/sample.pdf",
        )

    assert image_paths == fallback_paths
    assert image_assets == fallback_assets
    assert "using PyMuPDF fallback" in caplog.text


def test_extract_pdf_images_writes_supported_images(tmp_path, monkeypatch):
    reader = _ReaderStub([
        _PageStub([
            _ImageStub("img1.png", b"one"),
            _ImageStub("img2.png", b"two"),
        ])
    ])
    pymupdf_calls = []
    monkeypatch.setattr(
        pdf_parser,
        "_extract_pdf_images_with_pymupdf",
        lambda path, *, output_dir, page_number: pymupdf_calls.append((path, page_number)) or ([], []),
    )

    image_paths, image_assets = pdf_parser._extract_pdf_images(
        reader,
        output_dir=tmp_path,
        source_path="/tmp/sample.pdf",
    )

    assert len(image_paths) == 2
    assert Path(image_paths[0]).read_bytes() == b"one"
    assert Path(image_paths[1]).read_bytes() == b"two"
    assert pymupdf_calls == []
    assert image_assets == [
        {"path": image_paths[0], "page_number": 1},
        {"path": image_paths[1], "page_number": 1},
    ]
