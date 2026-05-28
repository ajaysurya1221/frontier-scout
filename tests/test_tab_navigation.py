"""v1.2 — navigation tests for the 2-tab Mission Control."""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed(path: Path) -> Path:
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    return path


def test_default_landing_tab_is_scout(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run())


def test_number_key_jumps_to_tab(tmp_path, monkeypatch):
    """Only 2 tabs in v1.2 — action_jump_tab(1) → Settings, action_jump_tab(0)
    → Scout. We invoke the action directly because the DataTable on Scout
    auto-focuses on mount and may swallow digit keystrokes in pilot tests."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_jump_tab(1)
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "settings"
            app.action_jump_tab(0)
            await pilot.pause()
            assert tc.active == "scout"

    asyncio.run(run())


def test_launch_with_tab_flag_lands_on_named_tab(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, initial_tab="settings")
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "settings"

    asyncio.run(run())


def test_unknown_tab_falls_back_to_scout(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, initial_tab="bogus")
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run())
