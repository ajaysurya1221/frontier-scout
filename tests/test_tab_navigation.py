"""Tab navigation tests — number-key jumps and --tab landing flag."""

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

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run())


def test_number_key_jumps_to_tab(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("4")
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "guard"
            await pilot.press("9")
            await pilot.pause()
            assert tc.active == "settings"

    asyncio.run(run())


def test_launch_with_tab_flag_lands_on_named_tab(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, show_splash=False, initial_tab="packs")
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "packs"

    asyncio.run(run())


def test_unknown_tab_falls_back_to_scout(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp
        from textual.widgets import TabbedContent

        app = SetupApp(diagnostics, show_splash=False, initial_tab="bogus")
        async with app.run_test() as pilot:
            await pilot.pause()
            tc = app.query_one(TabbedContent)
            assert tc.active == "scout"

    asyncio.run(run())
