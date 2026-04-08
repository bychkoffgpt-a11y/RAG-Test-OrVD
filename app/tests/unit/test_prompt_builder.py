from src.rag.prompt_builder import build_prompt


def test_build_prompt_includes_question_and_contexts():
    prompt = build_prompt(
        "Как восстановить доступ?",
        [
            {
                "text": "Шаг 1: открыть заявку.",
                "source_type": "csv_ans_docs",
                "doc_id": "DOC-1",
                "page_number": 2,
            },
            {
                "text": "Шаг 2: подтвердить личность.",
                "source_type": "internal_regulations",
                "doc_id": "REG-7",
                "page_number": None,
            },
        ],
    )

    assert "Как восстановить доступ?" in prompt
    assert "[1] Шаг 1: открыть заявку." in prompt
    assert "источник: csv_ans_docs/DOC-1, стр. 2" in prompt
    assert "[2] Шаг 2: подтвердить личность." in prompt
    assert "источник: internal_regulations/REG-7, стр. None" in prompt
