import pytest
from pydantic import ValidationError

from src.api.schemas import AskRequest, SourceItem


def test_ask_request_validates_min_question_length():
    with pytest.raises(ValidationError):
        AskRequest(question="hi")


def test_source_item_default_image_paths_is_empty_list():
    item = SourceItem(
        doc_id="doc-1",
        source_type="csv_ans_docs",
        chunk_id="chunk-1",
        score=0.99,
    )

    assert item.image_paths == []
