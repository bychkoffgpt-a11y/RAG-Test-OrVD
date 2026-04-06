import subprocess
from pathlib import Path


def convert_doc_to_docx(path: str) -> str:
    src = Path(path)
    out_dir = src.parent
    subprocess.run(
        ['soffice', '--headless', '--convert-to', 'docx', '--outdir', str(out_dir), str(src)],
        check=True,
    )
    return str(out_dir / f'{src.stem}.docx')
