from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisionCaseMetrics:
    recall: float
    hallucination: float


def recall(answer_text: str, golden_facts: list[str]) -> float:
    hay = answer_text.lower()
    hits = sum(1 for fact in golden_facts if fact.lower() in hay)
    return hits / len(golden_facts) if golden_facts else 0.0


def hallucination(answer_text: str, forbidden_facts: list[str]) -> float:
    hay = answer_text.lower()
    hits = sum(1 for fact in forbidden_facts if fact.lower() in hay)
    return hits / len(forbidden_facts) if forbidden_facts else 0.0


def evaluate_case(answer_text: str, golden_facts: list[str], forbidden_facts: list[str]) -> VisionCaseMetrics:
    return VisionCaseMetrics(
        recall=recall(answer_text=answer_text, golden_facts=golden_facts),
        hallucination=hallucination(answer_text=answer_text, forbidden_facts=forbidden_facts),
    )
