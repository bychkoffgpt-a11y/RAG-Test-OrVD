from pypdf import PdfReader


def parse_pdf(path: str) -> dict:
    reader = PdfReader(path)
    pages_text: list[str] = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or '')
    return {
        'pages': len(reader.pages),
        'text': '\n'.join(pages_text),
        'images': [],
    }
