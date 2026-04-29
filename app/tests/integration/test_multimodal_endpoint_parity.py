from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import app
import src.main as main_module
import src.api.ask as ask_module

from .vision_eval import evaluate_case


@dataclass
class _DummySource:
    doc_id: str = 'doc-1'
    source_type: str = 'csv_ans_docs'
    chunk_id: str = 'chunk-1'
    score: float = 0.9

    def model_dump(self):
        return {
            'doc_id': self.doc_id,
            'source_type': self.source_type,
            'chunk_id': self.chunk_id,
            'score': self.score,
        }


@dataclass
class _DummyVisual:
    image_path: str
    ocr_text: str
    summary: str = 'vision summary'
    confidence: float = 0.9

    def model_dump(self):
        return {
            'image_path': self.image_path,
            'ocr_text': self.ocr_text,
            'summary': self.summary,
            'confidence': self.confidence,
            'task_type': 'text',
        }


@dataclass
class _DummyAnswer:
    answer: str
    sources: list
    images: list
    visual_evidence: list


class _CaptureOrchestrator:
    def __init__(self):
        self.calls = []

    def answer(self, ask_payload, max_tokens=512, temperature=0.1, endpoint='/ask', pre_processing_sec=0.0):
        self.calls.append(
            {
                'question': ask_payload.question,
                'scope': ask_payload.scope,
                'attachments': [a.image_path for a in ask_payload.attachments],
                'max_tokens': max_tokens,
                'temperature': temperature,
                'endpoint': endpoint,
                'pre_processing_sec': pre_processing_sec,
            }
        )
        image_path = ask_payload.attachments[0].image_path if ask_payload.attachments else ''
        stem = Path(image_path).stem
        fact_map = {
            'tc_marker': 'ERR-9A7K-UNIQUE service timeout 500',
            'tc_ui_form': 'UHOP field validation failed request rejected',
        }
        answer_text = fact_map.get(stem, 'generic visual answer')
        visual = [_DummyVisual(image_path=image_path, ocr_text=answer_text)] if image_path else []
        return _DummyAnswer(answer=answer_text, sources=[_DummySource()], images=[], visual_evidence=visual)


def test_multimodal_payload_and_quality_parity_between_ask_and_chat(monkeypatch):
    dummy = _CaptureOrchestrator()
    monkeypatch.setattr(main_module, 'orch', dummy)
    monkeypatch.setattr(ask_module, 'orch', dummy)
    client = TestClient(app)

    cases = [
        {
            'image_path': '/tmp/tc_marker.png',
            'golden_facts': ['ERR-9A7K-UNIQUE', '500'],
            'forbidden_facts': ['stacktrace', 'database corrupted'],
        },
        {
            'image_path': '/tmp/tc_ui_form.png',
            'golden_facts': ['UHOP', 'validation'],
            'forbidden_facts': ['kernel panic', 'network ddos'],
        },
        {
            'image_path': '/tmp/tc_unknown.png',
            'golden_facts': ['generic', 'visual'],
            'forbidden_facts': ['password leaked', 'ransomware'],
        },
    ]

    ask_recall_scores = []
    chat_recall_scores = []
    ask_hallucination_scores = []
    chat_hallucination_scores = []

    for case in cases:
        ask_resp = client.post(
            '/ask',
            json={
                'question': 'Опиши проблему на скриншоте',
                'scope': 'all',
                'attachments': [{'image_path': case['image_path']}],
            },
        )
        assert ask_resp.status_code == 200
        ask_metrics = evaluate_case(
            answer_text=ask_resp.json()['answer'],
            golden_facts=case['golden_facts'],
            forbidden_facts=case['forbidden_facts'],
        )
        ask_recall_scores.append(ask_metrics.recall)
        ask_hallucination_scores.append(ask_metrics.hallucination)

        chat_resp = client.post(
            '/v1/chat/completions',
            json={
                'model': 'local-rag-model',
                'messages': [
                    {'role': 'system', 'content': 'Ты мультимодальный помощник.'},
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': 'Опиши проблему на скриншоте'},
                            {'type': 'image_url', 'image_url': {'url': f"file://{case['image_path']}"}},
                        ],
                    },
                ],
                'temperature': 0.0,
                'max_tokens': 256,
                'top_p': 0.2,
                'rag_scope': 'all',
            },
        )
        assert chat_resp.status_code == 200
        chat_answer = chat_resp.json()['choices'][0]['message']['content']
        chat_metrics = evaluate_case(
            answer_text=chat_answer,
            golden_facts=case['golden_facts'],
            forbidden_facts=case['forbidden_facts'],
        )
        chat_recall_scores.append(chat_metrics.recall)
        chat_hallucination_scores.append(chat_metrics.hallucination)

    assert len(dummy.calls) == len(cases) * 2
    ask_call, chat_call = dummy.calls[0], dummy.calls[1]
    assert ask_call['endpoint'] == '/ask'
    assert chat_call['endpoint'] == '/v1/chat/completions'
    assert ask_call['attachments'] == ['/tmp/tc_marker.png']
    assert chat_call['attachments'] == ['/tmp/tc_marker.png']
    assert chat_call['question'] == 'Опиши проблему на скриншоте'
    assert chat_call['max_tokens'] == 256
    assert chat_call['temperature'] == 0.0

    ask_recall_avg = sum(ask_recall_scores) / len(ask_recall_scores)
    chat_recall_avg = sum(chat_recall_scores) / len(chat_recall_scores)
    ask_hallucination_avg = sum(ask_hallucination_scores) / len(ask_hallucination_scores)
    chat_hallucination_avg = sum(chat_hallucination_scores) / len(chat_hallucination_scores)

    min_recall = 0.6
    recall_gap_threshold_pp = 0.10

    assert ask_recall_avg >= min_recall
    assert chat_recall_avg >= min_recall
    assert (ask_recall_avg - chat_recall_avg) <= recall_gap_threshold_pp
    assert ask_hallucination_avg == 0.0
    assert chat_hallucination_avg == 0.0


def test_chat_message_content_image_parts_are_not_lost(monkeypatch):
    dummy = _CaptureOrchestrator()
    monkeypatch.setattr(main_module, 'orch', dummy)
    client = TestClient(app)

    payload = {
        'model': 'local-rag-model',
        'messages': [
            {'role': 'system', 'content': 'sys'},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Вопрос по картинке'},
                    {'type': 'input_image', 'image_url': {'url': 'file:///tmp/first.png'}},
                    {'type': 'image', 'url': 'file:///tmp/second.png'},
                ],
            },
        ],
    }

    resp = client.post('/v1/chat/completions', json=payload)

    assert resp.status_code == 200
    assert dummy.calls
    assert dummy.calls[0]['attachments'] == ['/tmp/first.png', '/tmp/second.png']
