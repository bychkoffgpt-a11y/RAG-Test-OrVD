from docx import Document


def parse_docx(path: str) -> dict:
    doc = Document(path)
    lines = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return {
        'pages': None,
        'text': '\n'.join(lines),
        'images': [],
    }
