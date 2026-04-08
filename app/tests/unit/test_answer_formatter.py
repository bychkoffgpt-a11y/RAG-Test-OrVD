from src.rag.answer_formatter import collect_images


def test_collect_images_deduplicates_preserves_order():
    contexts = [
        {"image_paths": ["a.png", "b.png"]},
        {"image_paths": ["b.png", "c.png"]},
        {"image_paths": []},
        {},
    ]

    assert collect_images(contexts) == ["a.png", "b.png", "c.png"]
