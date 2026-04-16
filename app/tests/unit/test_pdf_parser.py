from pathlib import Path
import sys

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


class _PixmapStub:
    def __init__(self, payload: bytes):
        self.payload = payload

    def save(self, target):
        Path(target).write_bytes(self.payload)


class _PageFitzStub:
    def __init__(self, images):
        self._images = images

    def get_images(self, full=True):
        return self._images

    def get_pixmap(self, alpha=False):
        return _PixmapStub(b"rendered-page")


class _DocFitzStub:
    def __init__(self, page, extracted):
        self._page = page
        self._extracted = extracted

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def load_page(self, idx):
        return self._page

    def extract_image(self, xref):
        return self._extracted[xref]


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


def test_extract_pdf_images_uses_pymupdf_for_jb2_even_without_iterator_error(tmp_path, monkeypatch):
    reader = _ReaderStub([
        _PageStub([
            _ImageStub("page_1_1.jb2", b"ignored"),
        ])
    ])
    fallback_target = tmp_path / "page_1_1.png"
    fallback_target.write_bytes(b"fallback-raster")
    fallback_paths = [str(fallback_target)]
    fallback_assets = [{"path": str(fallback_target), "page_number": 1}]
    pymupdf_calls = []

    def _fallback(path, *, output_dir, page_number):
        pymupdf_calls.append((path, page_number))
        return fallback_paths, fallback_assets

    monkeypatch.setattr(pdf_parser, "_extract_pdf_images_with_pymupdf", _fallback)

    image_paths, image_assets = pdf_parser._extract_pdf_images(
        reader,
        output_dir=tmp_path,
        source_path="/tmp/sample.pdf",
    )

    assert image_paths == fallback_paths
    assert image_assets == fallback_assets
    assert pymupdf_calls == [("/tmp/sample.pdf", 1)]


def test_extract_pdf_images_with_pymupdf_renders_jb2_to_png(tmp_path, monkeypatch, caplog):
    page = _PageFitzStub(images=[(42,)])
    fake_doc = _DocFitzStub(
        page=page,
        extracted={42: {"ext": "jb2", "image": b"ignored"}},
    )
    fake_fitz = type("FakeFitzModule", (), {"open": lambda *_args, **_kwargs: fake_doc})
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    with caplog.at_level("WARNING"):
        image_paths, image_assets = pdf_parser._extract_pdf_images_with_pymupdf(
            "/tmp/sample.pdf",
            output_dir=tmp_path,
            page_number=1,
        )

    assert len(image_paths) == 1
    assert image_paths[0].endswith(".png")
    assert Path(image_paths[0]).read_bytes() == b"rendered-page"
    assert image_assets == [{"path": image_paths[0], "page_number": 1}]
    assert "rendering page raster for OCR compatibility" in caplog.text
