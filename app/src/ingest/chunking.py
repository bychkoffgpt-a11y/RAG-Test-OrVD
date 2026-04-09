import re


def _normalize_block(text: str) -> str:
    return ' '.join(text.split()).strip()


def _merge_blocks_with_overlap(blocks: list[str], chunk_size: int, overlap: int) -> list[str]:
    merged: list[str] = []
    current = ''

    for block in blocks:
        if not block:
            continue

        if len(block) > chunk_size:
            if current:
                merged.append(current)
                current = ''
            start = 0
            while start < len(block):
                end = min(start + chunk_size, len(block))
                merged.append(block[start:end])
                if end == len(block):
                    break
                start = max(0, end - overlap)
            continue

        if not current:
            current = block
            continue

        candidate = f'{current} {block}'
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            merged.append(current)
            current = block

    if current:
        merged.append(current)

    return merged


def _split_docs(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    heading_re = re.compile(r'^(\d+(\.\d+)*)?[)\.]?\s*[A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё0-9 \-–]{2,}$')

    blocks: list[str] = []
    current: list[str] = []

    for line in lines:
        is_heading = heading_re.match(line) and len(line.split()) <= 10
        if is_heading and current:
            blocks.append(_normalize_block('\n'.join(current)))
            current = [line]
        else:
            current.append(line)

    if current:
        blocks.append(_normalize_block('\n'.join(current)))

    return blocks


def _split_regs(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    clause_re = re.compile(r'^(\d+(\.\d+){0,3}|[IVXLCDM]+|[А-ЯЁA-Z])[\)\.]')
    section_re = re.compile(r'^(раздел|глава|статья|пункт)\b', re.IGNORECASE)

    blocks: list[str] = []
    current: list[str] = []

    for line in lines:
        starts_new = bool(clause_re.match(line) or section_re.match(line))
        if starts_new and current:
            blocks.append(_normalize_block('\n'.join(current)))
            current = [line]
        else:
            current.append(line)

    if current:
        blocks.append(_normalize_block('\n'.join(current)))

    return blocks


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120, strategy: str = 'fixed') -> list[str]:
    if overlap >= chunk_size:
        raise ValueError('overlap должен быть меньше chunk_size')

    normalized = text.strip()
    if not normalized:
        return []

    if strategy == 'docs':
        blocks = _split_docs(normalized)
    elif strategy == 'regs':
        blocks = _split_regs(normalized)
    else:
        blocks = [_normalize_block(normalized)]

    if not blocks:
        return []

    return _merge_blocks_with_overlap(blocks, chunk_size=chunk_size, overlap=overlap)
