from pathlib import Path

from print_vlm_faceoff import _format_hint


def test_format_hint_suggests_results_file_for_summary_input(tmp_path: Path) -> None:
    summary = tmp_path / "vlm_chat_score_v2_summary.json"
    summary.write_text("{}", encoding="utf-8")
    results = tmp_path / "vlm_chat_results.jsonl"
    results.write_text('{"id":"x","answer_text":"ok"}\n', encoding="utf-8")

    hint = _format_hint(summary)

    assert "Detected summary file" in hint
    assert str(results) in hint
