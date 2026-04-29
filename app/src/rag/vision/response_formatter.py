from src.api.schemas import AskResponse
from src.rag.answer_formatter import append_grounding_markdown, append_sources_markdown


def format_runtime_response(
    answer: AskResponse,
    *,
    base_url: str | None = None,
    is_vision_only: bool = False,
) -> dict:
    rendered_answer = answer.answer
    if not is_vision_only:
        rendered_answer = append_grounding_markdown(rendered_answer, answer.sources, base_url=base_url)
        rendered_answer = append_sources_markdown(rendered_answer, answer.sources, base_url=base_url)

    return {
        'answer': rendered_answer,
        'sources': [s.model_dump() for s in answer.sources],
        'images': answer.images,
        'visual_evidence': [item.model_dump() for item in answer.visual_evidence],
    }
