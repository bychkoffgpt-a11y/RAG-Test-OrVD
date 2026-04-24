import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from src.core.settings import settings


logger = logging.getLogger(__name__)


class TraceCardWriter:
    def __init__(self) -> None:
        self.enabled = settings.rag_ui_trace_enabled
        self.base_dir = Path(settings.rag_ui_trace_dir)

    def write(self, card: dict) -> dict | None:
        if not self.enabled:
            return None

        now = datetime.now(timezone.utc)
        request_id = str(card.get('meta', {}).get('request_id') or 'no-request-id')
        safe_request_id = re.sub(r'[^a-zA-Z0-9._-]+', '-', request_id).strip('-') or 'request'
        day_dir = self.base_dir / now.strftime('%Y') / now.strftime('%m') / now.strftime('%d')
        day_dir.mkdir(parents=True, exist_ok=True)

        slug = f"{now.strftime('%H%M%S_%f')}_{safe_request_id}"
        json_path = day_dir / f'{slug}.json'
        md_path = day_dir / f'{slug}.md'

        card['meta'] = {
            **card.get('meta', {}),
            'trace_generated_at': now.isoformat(),
            'json_path': str(json_path),
            'markdown_path': str(md_path),
        }

        json_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding='utf-8')
        md_path.write_text(self._render_markdown(card), encoding='utf-8')

        logger.info('rag_trace_card_written', extra={'json_path': str(json_path), 'markdown_path': str(md_path)})
        return {'json_path': str(json_path), 'markdown_path': str(md_path)}

    def _render_markdown(self, card: dict) -> str:
        meta = card.get('meta', {})
        payload = card.get('input', {})
        stages = card.get('stages', {})
        timings = card.get('aggregate_timings_sec', {})

        lines: list[str] = []
        lines.append('# RAG UI trace card')
        lines.append('')
        lines.append('## Meta')
        lines.append(f"- request_id: `{meta.get('request_id', '')}`")
        lines.append(f"- endpoint: `{meta.get('endpoint', '')}`")
        lines.append(f"- generated_at: `{meta.get('trace_generated_at', '')}`")
        lines.append('')

        lines.append('## Input')
        lines.append(f"- question: {payload.get('question', '')}")
        lines.append(f"- scope: `{payload.get('scope', '')}`")
        lines.append(f"- top_k: `{payload.get('top_k', '')}`")
        lines.append(f"- attachments: `{len(payload.get('attachments', []) or [])}`")
        lines.append('')

        lines.append('## Stage timings (sec)')
        if timings:
            for key, value in timings.items():
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append('- (empty)')
        lines.append('')

        lines.append('## Vision')
        vision = stages.get('vision', {})
        lines.append(f"- mode: `{vision.get('vision_runtime_mode', '')}`")
        lines.append(f"- prompt: `{vision.get('vision_prompt', '')}`")
        lines.append(f"- evidence_count: `{len(vision.get('visual_evidence', []) or [])}`")
        lines.append('')

        lines.append('## Retrieval and rerank')
        retrieval = stages.get('retrieval', {})
        lines.append(f"- candidate_limit: `{retrieval.get('query', {}).get('candidate_limit', '')}`")
        lines.append(f"- deduped_count: `{retrieval.get('deduped_count', '')}`")
        lines.append(f"- filtered_count: `{retrieval.get('filtered_count', '')}`")
        lines.append(f"- returned_count: `{retrieval.get('returned_count', '')}`")
        lines.append(f"- reranker_applied: `{retrieval.get('reranker', {}).get('applied', False)}`")
        lines.append('')

        lines.append('## Prompt and answer')
        prompt = stages.get('prompt', {}).get('final_prompt', '')
        lines.append('```text')
        lines.append(prompt)
        lines.append('```')
        lines.append('')

        answer = stages.get('llm', {}).get('answer', '')
        lines.append('```text')
        lines.append(answer)
        lines.append('```')
        lines.append('')

        return '\n'.join(lines).strip() + '\n'
