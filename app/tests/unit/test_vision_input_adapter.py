from src.rag.vision.input_adapter import adapt_image_attachments


def test_adapter_returns_identical_output_for_equivalent_ask_and_chat_payload(monkeypatch):
    monkeypatch.setattr('src.rag.vision.input_adapter.settings.vision_runtime_max_images', 10, raising=False)

    image_path = 'file:///tmp/image-a.png'
    ask_result = adapt_image_attachments(ask_attachments=[{'image_path': image_path}])
    chat_result = adapt_image_attachments(
        message_content=[{'type': 'image_url', 'image_url': {'url': image_path}}],
    )

    assert [item.model_dump() for item in ask_result] == [item.model_dump() for item in chat_result]
    assert ask_result[0].image_path == '/tmp/image-a.png'


def test_adapter_normalizes_order_dedup_and_limits(monkeypatch):
    monkeypatch.setattr('src.rag.vision.input_adapter.settings.vision_runtime_max_images', 2, raising=False)

    result = adapt_image_attachments(
        message_content=[
            {'type': 'image_url', 'image_url': {'url': 'file:///tmp/first.png'}},
            {'type': 'input_image', 'image_url': {'url': 'file:///tmp/first.png'}},
            {'type': 'image_url', 'image_url': {'url': 'file:///tmp/second.png'}},
            {'type': 'image_url', 'image_url': {'url': 'file:///tmp/third.png'}},
        ]
    )

    assert [item.image_path for item in result] == ['/tmp/first.png', '/tmp/second.png']
