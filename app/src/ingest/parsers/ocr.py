import subprocess


def ocr_pdf_rus(path: str) -> str:
    # Заглушка: при необходимости расширяется до полноценного OCR pipeline.
    result = subprocess.run(
        ['tesseract', path, 'stdout', '-l', 'rus+eng'],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout or ''
