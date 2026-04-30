from pathlib import Path

from print_vlm_faceoff import _format_hint, extract_scoring_text


def test_format_hint_suggests_results_file_for_summary_input(tmp_path: Path) -> None:
    summary = tmp_path / "vlm_chat_score_v2_summary.json"
    summary.write_text("{}", encoding="utf-8")
    results = tmp_path / "vlm_chat_results.jsonl"
    results.write_text('{"id":"x","answer_text":"ok"}\n', encoding="utf-8")

    hint = _format_hint(summary)

    assert "Detected summary file" in hint
    assert str(results) in hint


def test_extract_scoring_text_prefers_visual_evidence_when_answer_empty() -> None:
    row = {
        "answer_text": "",
        "raw_response": {
            "visual_evidence": [
                {"ocr_text": "Invoice #123", "summary": "Amount 849,90", "task_type": "text"}
            ]
        },
    }
    text, scored_from = extract_scoring_text(row)
    assert "Invoice #123" in text
    assert scored_from == "visual_evidence"


def test_extract_scoring_text_prefers_visual_evidence_when_both_present() -> None:
    row = {
        "answer_text": "generic fallback answer",
        "raw_response": {
            "visual_evidence": [{"ocr_text": "STOP sign", "summary": "red octagon", "task_type": "sign"}]
        },
    }
    text, scored_from = extract_scoring_text(row)
    assert "STOP sign" in text
    assert "generic fallback answer" not in text
    assert scored_from == "visual_evidence"


def test_extract_scoring_text_fallback_answer_text_when_no_sources() -> None:
    row = {"answer_text": "", "raw_response": {}}
    text, scored_from = extract_scoring_text(row)
    assert text == ""
    assert scored_from == "answer_text"
