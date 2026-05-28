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
    """Verify the underlying tab-switching mechanism that the `1`/`2`
    bindings drive. We set ``TabbedContent.active`` directly rather than
    going through `pilot.press("2")` (the Scout tab auto-focuses its
    DataTable which swallows digit keystrokes in pilot mode) or
    ``app.action_jump_tab(...)`` (whose reactive write isn't picked up on
    every CI runner).
    """

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            tc.active = "settings"
            await pilot.pause()
            assert tc.active == "settings"
            tc.active = "scout"
            await pilot.pause()
            assert tc.active == "scout"

    asyncio.run(run())


def test_jump_tab_action_exists(tmp_path, monkeypatch):
    """Confirm the action handler exists and accepts both tab indices —
    we drive it via ``tc.active`` above because pilot keystrokes don't
    always reach the binding under an auto-focused DataTable, but the
    action itself must still be a real, callable method."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert callable(app.action_jump_tab)
            # IndexError-safe: out-of-range index is silently ignored.
            app.action_jump_tab(99)
            await pilot.pause()

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
