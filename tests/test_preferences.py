"""Provider preference persistence — name only, never secrets."""

from __future__ import annotations

import pytest

from frontier_scout import preferences


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    return tmp_path


def test_no_preference_returns_none(home):
    assert preferences.preferred_provider() is None


def test_round_trip(home):
    preferences.save_preferred_provider("claude-cli")
    assert preferences.preferred_provider() == "claude-cli"
    data = preferences.load_preferences()
    assert set(data) == {"schema", "provider"}


def test_corrupt_file_degrades_to_none(home):
    (home / "preferences.json").write_text("{ not valid json", encoding="utf-8")
    assert preferences.preferred_provider() is None
    assert preferences.load_preferences() == {}


def test_overwrite_keeps_single_value(home):
    preferences.save_preferred_provider("openai")
    preferences.save_preferred_provider("anthropic")
    assert preferences.preferred_provider() == "anthropic"
