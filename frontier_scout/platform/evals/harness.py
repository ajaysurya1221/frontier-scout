"""Small deterministic eval harness for Incident Change Scout."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class EvalCase(BaseModel):
    id: str
    question: str
    required_terms: list[str]
    min_citations: int = 2


class EvalScore(BaseModel):
    case_id: str
    passed: bool
    score: float
    reasons: list[str]


def load_cases(path: Path) -> list[EvalCase]:
    return [EvalCase(**row) for row in json.loads(path.read_text())]


def grade_answer(case: EvalCase, answer: str, citation_count: int) -> EvalScore:
    reasons: list[str] = []
    term_hits = sum(1 for term in case.required_terms if term.lower() in answer.lower())
    if term_hits < len(case.required_terms):
        reasons.append("missing required terms")
    if citation_count < case.min_citations:
        reasons.append("not enough citations")
    score = 0.7 * (term_hits / max(1, len(case.required_terms))) + 0.3 * min(1.0, citation_count / case.min_citations)
    return EvalScore(case_id=case.id, passed=not reasons and score >= 0.8, score=round(score, 3), reasons=reasons)

