from src.rag.trace_card import TraceCardWriter


def test_trace_card_markdown_renders_vision_diagnostics():
    writer = TraceCardWriter()
    card = {
        'meta': {'request_id': 'r1', 'endpoint': '/ask', 'trace_generated_at': '2026-05-02T00:00:00Z'},
        'input': {'question': 'q', 'scope': 'all', 'top_k': 8, 'attachments': []},
        'aggregate_timings_sec': {'total': 0.1},
        'stages': {
            'vision': {
                'vision_runtime_mode': 'vlm',
                'vision_prompt': 'p',
                'visual_evidence': [
                    {
                        'vlm_output_format': 'raw',
                        'vlm_json_parse_ok': False,
                        'vlm_raw_length': 512,
                        'vlm_fallback_applied': True,
                        'vlm_max_new_tokens_used': 384,
                    }
                ],
            }
        },
    }
    markdown = writer._render_markdown(card)
    assert '## Vision diagnostics' in markdown
    assert 'vlm_output_format: `raw`' in markdown
    assert 'vlm_json_parse_ok: `False`' in markdown
    assert 'vlm_raw_length: `512`' in markdown
    assert 'vlm_fallback_applied: `True`' in markdown
    assert 'vlm_max_new_tokens_used: `384`' in markdown
