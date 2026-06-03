"""TUI provider surface — pure helpers (no Pilot)."""

from __future__ import annotations

import pytest

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import _failure_compass, _provider_reason_label
from frontier_scout.tui3.overlays import ProviderSwitcherScreen
from frontier_scout.tui3.state import AppState


def test_appstate_has_provider_reason():
    s = AppState(repo="/x", repo_name="x")
    assert s.provider_reason == ""
    assert s.with_(provider_reason="auto").provider_reason == "auto"


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("flag", " · pinned"),
        ("preference", " · pinned"),
        ("auto", " · detected"),
        ("demo", ""),
        ("none", ""),
        ("must_ask", ""),
    ],
)
def test_reason_label(reason, expected):
    assert _provider_reason_label(reason) == expected


def test_detect_provider_demo():
    assert data._detect_provider(demo=True) == ("local", "demo")


def test_detect_provider_none(monkeypatch):
    for v in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "FRONTIER_SCOUT_PROVIDER",
    ):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("frontier_scout.providers._has_claude_cli", lambda: False)
    monkeypatch.setattr("frontier_scout.providers._has_codex_cli", lambda: False)
    assert data._detect_provider(demo=False) == ("local", "none")


def test_provider_choices_marks_active_and_availability(monkeypatch):
    monkeypatch.setattr(
        "frontier_scout.providers.available_providers", lambda: ["claude-cli"]
    )
    rows = data.provider_choices(current="claude-cli")
    by_id = {r["id"]: r for r in rows}
    assert by_id["claude-cli"]["available"] and by_id["claude-cli"]["active"]
    assert not by_id["openai"]["available"]
    assert by_id["openai"]["hint"]  # tells the user how to enable it
    assert by_id["openai-compatible"]["label"] == "Custom endpoint (your gateway)"


def test_switcher_only_selects_available():
    choices = [
        {
            "id": "anthropic",
            "label": "Anthropic API",
            "available": False,
            "hint": "set key",
            "active": False,
        },
        {
            "id": "claude-cli",
            "label": "Claude (CLI subscription)",
            "available": True,
            "hint": "",
            "active": True,
        },
    ]
    scr = ProviderSwitcherScreen(choices)
    assert scr._selectable() == [1]  # the unavailable row is skipped
    assert scr._sel == 1  # starts on the active/available row
    assert "set key" in scr._list_markup()  # unavailable row shows its hint


def test_failure_compass_offers_recovery_for_scout():
    msg = _failure_compass("scout", "claude CLI timed out after 180s")
    assert "timed out" in msg
    assert "switch" in msg and "retry" in msg and "--demo" in msg


def test_failure_compass_plain_for_other_kinds():
    msg = _failure_compass("guard", "boom")
    assert "boom" in msg
    assert "retry" not in msg  # recovery affordance is scout-specific


def test_switcher_two_line_cost_rows():
    """Cost-aware two-line rows: cost + detail for available, 'fix: <hint>' for
    unavailable, and an 'active · <reason>' pill on the active engine."""
    choices = [
        {
            "id": "claude-cli",
            "label": "Claude (CLI subscription)",
            "available": True,
            "hint": "",
            "active": True,
        },
        {
            "id": "openai",
            "label": "OpenAI API",
            "available": False,
            "hint": "set OPENAI_API_KEY",
            "active": False,
        },
    ]
    scr = ProviderSwitcherScreen(choices, meta=data.providers(), reason="preference")
    md = scr._list_markup()
    assert "$0 marginal" in md  # claude-cli cost from data.providers()
    assert "active" in md and "pinned" in md  # active pill carries the reason word
    assert "PATH" in md  # claude-cli detail line ("`claude` on/not on PATH")
    assert "fix: set OPENAI_API_KEY" in md  # unavailable row → fix line


def test_switcher_reason_word_maps_auto_to_detected():
    choices = [
        {"id": "anthropic", "label": "Anthropic API", "available": True, "hint": "", "active": True},
    ]
    scr = ProviderSwitcherScreen(choices, meta=data.providers(), reason="auto")
    assert "detected" in scr._list_markup()
