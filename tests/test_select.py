"""The single provider-selection ladder used by both TUI and headless CLI."""
from __future__ import annotations

import pytest

from frontier_scout.providers import select as sel


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                "FRONTIER_SCOUT_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    sel.reset_provider()


def test_flag_wins(monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_PROVIDER", "openai")
    s = sel.select()
    assert (s.name, s.reason) == ("openai", "flag")


def test_saved_preference(monkeypatch):
    from frontier_scout import preferences
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # pragma: allowlist secret
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    preferences.save_preferred_provider("claude-cli")
    s = sel.select()
    assert (s.name, s.reason) == ("claude-cli", "preference")


def test_preference_ignored_when_unavailable(monkeypatch):
    from frontier_scout import preferences
    preferences.save_preferred_provider("claude-cli")  # not on PATH per fixture
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    s = sel.select()
    assert (s.name, s.reason) == ("openai", "auto")


def test_must_ask_when_ambiguous_and_interactive(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # pragma: allowlist secret
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: True)
    assert sel.select(interactive=True).reason == "must_ask"
    assert sel.select(interactive=False).reason == "auto"


def test_auto_single(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "y")  # pragma: allowlist secret
    assert sel.select().name == "openai"


def test_none_available():
    assert sel.select().reason == "none"
