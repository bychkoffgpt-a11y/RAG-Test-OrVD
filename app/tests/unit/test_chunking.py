from src.ingest.chunking import chunk_text


def test_chunk_text_non_empty():
    text = 'a' * 2500
    chunks = chunk_text(text, chunk_size=900, overlap=120)
    assert len(chunks) >= 3


def test_chunk_text_regs_strategy_splits_clauses():
    text = '\n'.join(
        [
            'Раздел 1 Общие положения',
            '1. Первый пункт с вводной нормой.',
            '2. Второй пункт с уточнением.',
            '3. Третий пункт с исключением.',
        ]
    )
    chunks = chunk_text(text, chunk_size=70, overlap=20, strategy='regs')
    assert len(chunks) >= 2
    assert any('1. Первый пункт' in chunk for chunk in chunks)


def test_chunk_text_docs_strategy_splits_headings():
    text = '\n'.join(
        [
            'Настройка рабочего места',
            'Установите клиент и проверьте подключение.',
            'Диагностика ошибок',
            'Проверьте журналы, сетевые настройки и перезапуск сервиса.',
        ]
    )
    chunks = chunk_text(text, chunk_size=110, overlap=15, strategy='docs')
    assert len(chunks) >= 2


def test_chunk_text_invalid_overlap():
    text = 'короткий текст'
    try:
        chunk_text(text, chunk_size=100, overlap=100)
    except ValueError as exc:
        assert 'overlap' in str(exc)
    else:
        raise AssertionError('Ожидался ValueError при overlap >= chunk_size')


def test_chunk_text_splits_long_block_near_sentence_boundary():
    text = (
        'Это длинное предложение для проверки разбиения. '
        'Второе предложение должно попасть в следующий чанк без обрезки слов. '
        'Третье предложение завершает абзац.'
    )
    chunks = chunk_text(text, chunk_size=90, overlap=15)

    assert len(chunks) >= 2
    assert not any(chunk.endswith('следую') for chunk in chunks)
