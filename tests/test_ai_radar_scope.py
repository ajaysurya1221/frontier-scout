"""Stream 2 — AI-radar scope guardrail.

Frontier Scout is an AI-adoption radar. A real-use scout surfaced FastAPI
and other generic web frameworks in the AI-tools feed. The fix is two-layer:

1. LLM rubric guardrails (scripts/prompts.py + scripts/tools.py) tell the
   scorer/judge that generic infrastructure is dependency-scan material.
2. A deterministic backstop (``frontier_scout.scout.drop_non_ai_native``)
   filters the live verdict list so a mislabelled framework never reaches
   the AI feed.

These tests pin the deterministic backstop and assert the rubric text carries
the scope language.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from frontier_scout.scout import _is_ai_native, drop_non_ai_native  # noqa: E402


def _v(name: str, **extra) -> dict:
    base = {"tool_name": name, "verdict": "assess", "category": "dev_tool"}
    base.update(extra)
    return base


def test_fastapi_is_dropped():
    assert _is_ai_native(_v("FastAPI")) is False
    assert _is_ai_native(_v("FastAPI 0.115.0")) is False
    assert _is_ai_native(_v("tiangolo/fastapi")) is False


def test_other_generic_infra_dropped():
    for name in ("flask", "Django 5.0", "requests", "SQLAlchemy", "webpack", "Next.js"):
        assert _is_ai_native(_v(name)) is False, name


def test_real_ai_tools_kept():
    for name in ("anthropics/skills", "langgraph", "postgres-mcp", "crewai", "dspy"):
        assert _is_ai_native(_v(name)) is True, name


def test_framework_with_ai_capability_is_kept():
    # A FastAPI release that ships a first-class MCP endpoint stays in scope.
    v = _v("FastAPI", what="Adds a native MCP server endpoint for agent tool-calling.")
    assert _is_ai_native(v) is True


def test_ai_signal_via_tags_keeps_item():
    v = _v("flask", tags=["llm", "rag"])
    assert _is_ai_native(v) is True


def test_drop_non_ai_native_filters_list():
    verdicts = [
        _v("FastAPI"),
        _v("langgraph"),
        _v("requests"),
        _v("anthropics/skills"),
    ]
    kept = drop_non_ai_native(verdicts)
    names = {v["tool_name"] for v in kept}
    assert names == {"langgraph", "anthropics/skills"}


def test_empty_and_missing_name_safe():
    assert drop_non_ai_native([]) == []
    assert _is_ai_native({}) is True  # no name → not infra → keep (conservative)


def test_rubric_carries_scope_language():
    from tools import SCORE_ITEMS_TOOL

    from prompts import CATEGORIES, JUDGE_RUBRIC

    score_desc = SCORE_ITEMS_TOOL["description"].lower()
    assert "ai-radar scope" in score_desc or "ai-adoption radar" in score_desc
    assert "fastapi" in score_desc
    assert "fastapi" in JUDGE_RUBRIC.lower()
    assert "ai-native" in CATEGORIES.lower() or "ai-adoption radar" in CATEGORIES.lower()
