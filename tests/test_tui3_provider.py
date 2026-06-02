"""TUI provider surface — pure helpers (no Pilot)."""
from __future__ import annotations

import pytest

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import _provider_reason_label
from frontier_scout.tui3.state import AppState


def test_appstate_has_provider_reason():
    s = AppState(repo="/x", repo_name="x")
    assert s.provider_reason == ""
    assert s.with_(provider_reason="auto").provider_reason == "auto"


@pytest.mark.parametrize("reason,expected", [
    ("flag", " · pinned"), ("preference", " · pinned"),
    ("auto", " · auto"), ("demo", ""), ("none", ""), ("must_ask", ""),
])
def test_reason_label(reason, expected):
    assert _provider_reason_label(reason) == expected


def test_detect_provider_demo():
    assert data._detect_provider(demo=True) == ("local", "demo")


def test_detect_provider_none(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
              "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    assert data._detect_provider(demo=False) == ("local", "none")
