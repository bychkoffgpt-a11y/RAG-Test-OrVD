from unittest.mock import patch, MagicMock

import pytest

from src.telemetry.metrics import observe_rag_stage_latency, metrics_response


# ---------------------------------------------------------------------------
# observe_rag_stage_latency
# ---------------------------------------------------------------------------

def test_observe_rag_stage_latency_calls_histogram_with_correct_labels():
    mock_histogram = MagicMock()
    mock_labels = MagicMock()
    mock_histogram.labels.return_value = mock_labels

    with patch('src.telemetry.metrics.RAG_STAGE_LATENCY', mock_histogram):
        observe_rag_stage_latency(
            endpoint='/ask',
            stage='retrieval',
            has_attachments=True,
            scope='all',
            vision_mode='ocr',
            duration_sec=1.23,
            case_type='text',
        )

    mock_histogram.labels.assert_called_once_with(
        endpoint='/ask',
        stage='retrieval',
        has_attachments='1',
        scope='all',
        vision_mode='ocr',
        case_type='text',
    )
    mock_labels.observe.assert_called_once_with(1.23)


def test_observe_rag_stage_latency_has_attachments_false_becomes_zero():
    mock_histogram = MagicMock()
    mock_histogram.labels.return_value = MagicMock()

    with patch('src.telemetry.metrics.RAG_STAGE_LATENCY', mock_histogram):
        observe_rag_stage_latency(
            endpoint='/v1/chat/completions',
            stage='llm_generation',
            has_attachments=False,
            scope='csv_ans_docs',
            vision_mode='disabled',
            duration_sec=0.5,
            case_type='text_only',
        )

    call_kwargs = mock_histogram.labels.call_args[1]
    assert call_kwargs['has_attachments'] == '0'


def test_observe_rag_stage_latency_clamps_negative_duration_to_zero():
    mock_histogram = MagicMock()
    mock_labels = MagicMock()
    mock_histogram.labels.return_value = mock_labels

    with patch('src.telemetry.metrics.RAG_STAGE_LATENCY', mock_histogram):
        observe_rag_stage_latency(
            endpoint='/ask',
            stage='pre_processing',
            has_attachments=False,
            scope='all',
            vision_mode='ocr',
            duration_sec=-0.5,
            case_type='text_only',
        )

    observed_value = mock_labels.observe.call_args[0][0]
    assert observed_value == 0.0


# ---------------------------------------------------------------------------
# metrics_response
# ---------------------------------------------------------------------------

def test_metrics_response_returns_response_with_correct_content_type():
    from prometheus_client import CONTENT_TYPE_LATEST

    response = metrics_response()

    assert response.media_type == CONTENT_TYPE_LATEST


def test_metrics_response_body_is_bytes():
    response = metrics_response()

    assert isinstance(response.body, bytes)
    assert len(response.body) > 0
