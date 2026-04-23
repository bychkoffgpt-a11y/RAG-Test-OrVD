from src.rag.answer_formatter import append_grounding_markdown, append_sources_markdown, collect_images


def test_collect_images_deduplicates_preserves_order():
    contexts = [
        {'image_paths': ['a.png', 'b.png']},
        {'image_paths': ['b.png', 'c.png']},
        {'image_paths': []},
        {},
    ]

    assert collect_images(contexts) == ['a.png', 'b.png', 'c.png']


class _Source:
    def __init__(self, source_type: str, doc_id: str, download_url: str):
        self.source_type = source_type
        self.doc_id = doc_id
        self.download_url = download_url


def test_append_sources_markdown_adds_download_links_without_duplicates():
    sources = [
        _Source('internal_regulations', 'DOC-1', '/sources/internal_regulations/DOC-1/download'),
        _Source('internal_regulations', 'DOC-1', '/sources/internal_regulations/DOC-1/download'),
        _Source('csv_ans_docs', 'DOC-2', '/sources/csv_ans_docs/DOC-2/download'),
    ]

    rendered = append_sources_markdown('Ответ', sources)

    assert 'Источники для скачивания' in rendered
    assert rendered.count('internal_regulations/DOC-1: [скачать документ](/sources/internal_regulations/DOC-1/download)') == 1
    assert '- csv_ans_docs/DOC-2: [скачать документ](/sources/csv_ans_docs/DOC-2/download)' in rendered


def test_append_sources_markdown_uses_absolute_urls_with_base_url():
    sources = [
        _Source('csv_ans_docs', 'DOC-2', '/sources/csv_ans_docs/DOC-2/download'),
    ]

    rendered = append_sources_markdown('Ответ', sources, base_url='http://localhost:8000/')

    assert '- csv_ans_docs/DOC-2: [скачать документ](http://localhost:8000/sources/csv_ans_docs/DOC-2/download)' in rendered


def test_append_sources_markdown_encodes_spaces_in_document_url():
    sources = [
        _Source(
            'csv_ans_docs',
            'Инструкция по работе',
            '/sources/csv_ans_docs/Инструкция по работе/download',
        ),
    ]

    rendered = append_sources_markdown('Ответ', sources, base_url='http://localhost:8000/')

    assert (
        '- csv_ans_docs/Инструкция по работе: '
        '[скачать документ](http://localhost:8000/sources/csv_ans_docs/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F%20%D0%BF%D0%BE%20%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D0%B5/download)'
    ) in rendered


def test_append_grounding_markdown_renders_structured_foundation_with_links():
    sources = [
        _Source('csv_ans_docs', 'DOC-2', '/sources/csv_ans_docs/DOC-2/download'),
        _Source('csv_ans_docs', 'DOC-2', '/sources/csv_ans_docs/DOC-2/download'),
        _Source('internal_regulations', 'REG-1', '/sources/internal_regulations/REG-1/download'),
    ]
    sources[0].page_number = 3
    sources[1].page_number = 3
    sources[2].page_number = None

    rendered = append_grounding_markdown('Ответ', sources, base_url='http://localhost:8000/')

    assert 'Основание:' in rendered
    assert '1. csv_ans_docs/DOC-2, стр. 3: [скачать документ](http://localhost:8000/sources/csv_ans_docs/DOC-2/download)' in rendered
    assert '2. internal_regulations/REG-1: [скачать документ](http://localhost:8000/sources/internal_regulations/REG-1/download)' in rendered


def test_append_sources_markdown_strips_model_generated_reference_tail():
    answer = 'Шаги решения.\n\nОснование:\n1. [1], [2], [3]'
    sources = [_Source('csv_ans_docs', 'DOC-2', '/sources/csv_ans_docs/DOC-2/download')]
    rendered = append_grounding_markdown(answer, sources)
    rendered = append_sources_markdown(rendered, sources)

    assert '[1], [2], [3]' not in rendered
    assert 'Источники для скачивания' in rendered
