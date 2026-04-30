from src.rag.prompt_builder import build_vision_prompt


def test_build_vision_prompt_snapshot():
    prompt = build_vision_prompt(
        'Почему система вернула ошибку?',
        visual_evidence=[
            {
                'summary': 'На форме показан код ошибки',
                'ocr_text': 'ERROR 500\nRequest ID: ABC-123',
                'confidence': 0.92,
                'image_path': '/tmp/ui_error.png',
            }
        ],
    )

    expected = (
        'Вопрос:\n'
        'Почему система вернула ошибку?\n\n'
        'Сигналы со скриншотов:\n'
        '[IMG-1] На форме показан код ошибки (confidence=0.92, path=/tmp/ui_error.png)\n'
        'OCR:\n'
        'ERROR 500\n'
        'Request ID: ABC-123'
    )

    assert prompt == expected
