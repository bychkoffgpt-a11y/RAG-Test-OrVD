import re


def _normalize_block(text: str) -> str:
    return ' '.join(text.split()).strip()


def _split_long_block(block: str, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    text_len = len(block)

    while start < text_len:
        target_end = min(start + chunk_size, text_len)
        end = target_end

        if target_end < text_len:
            window = block[start:target_end]
            sentence_break = max(window.rfind('.'), window.rfind('!'), window.rfind('?'), window.rfind(';'))
            if sentence_break >= int(len(window) * 0.55):
                end = start + sentence_break + 1
            else:
                word_break = window.rfind(' ')
                if word_break >= int(len(window) * 0.55):
                    end = start + word_break

        chunk = block[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        next_start = max(0, end - overlap)
        while next_start > 0 and not block[next_start - 1].isspace() and not block[next_start].isspace():
            next_start -= 1
        while next_start < text_len and block[next_start].isspace():
            next_start += 1
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


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
            merged.extend(_split_long_block(block, chunk_size=chunk_size, overlap=overlap))
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
