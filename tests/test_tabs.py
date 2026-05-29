"""v1.2 — tab-mount tests for the simplified Scout + Settings layout."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed_repo(path: Path) -> Path:
    path.mkdir()
    (path / "AGENTS.md").write_text("# rules\n")
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    (path / "Dockerfile").write_text("FROM python:3.12\n")
    return path


def _app(tmp_path: Path, *, initial_tab: str = "scout"):
    diagnostics = setup_diagnostics(_seed_repo(tmp_path / "repo"), ollama_timeout_s=0.001)

    from frontier_scout.tui.setup_app import SetupApp

    return SetupApp(diagnostics, initial_tab=initial_tab)


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------


def test_scout_tab_populates_when_run_button_pressed(tmp_path, monkeypatch):
    """v1.3.0 Stream C — the table is empty until ▶ Scout now is
    pressed (no more auto-fire on mount). Cursor lands on row 0
    after the worker completes."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import DataTable

            table = app.query_one("#scout-table", DataTable)
            assert table.row_count == 0  # auto-fire is dead
            await pilot.click("#scout-run")
            for _ in range(80):
                await pilot.pause()
                if table.row_count > 0:
                    break
            assert table.row_count >= 1
            assert table.cursor_row == 0

    asyncio.run(run())


def test_scout_detail_panel_populates_after_run(tmp_path, monkeypatch):
    """v1.3.0 Stream C — detail panel renders the first verdict's
    reasoning after the user explicitly runs a scout."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import DataTable, Static

            await pilot.click("#scout-run")
            for _ in range(80):
                await pilot.pause()
                table = app.query_one("#scout-table", DataTable)
                if table.row_count > 0:
                    break
            await pilot.pause()
            detail = str(app.query_one("#scout-detail", Static).render())
            assert "What" in detail or "Why" in detail
            assert "Scouting" not in detail or "Why" in detail

    asyncio.run(run())


def test_scout_dismiss_persists(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import Button, DataTable

            await pilot.click("#scout-run")
            for _ in range(80):
                await pilot.pause()
                if app.query_one("#scout-table", DataTable).row_count > 0:
                    break
            app.query_one("#scout-dismiss", Button).press()
            await pilot.pause()

            from frontier_scout.store import setup_state_path

            state = json.loads(setup_state_path().read_text())
            assert state.get("dismissed_tools")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Settings — every render must tolerate broken state without crashing
# ---------------------------------------------------------------------------


def test_settings_tab_mounts(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="settings")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button

            # All buttons mount without crashing the tab.
            for bid in (
                "settings-policy-home",
                "settings-policy-repo",
                "settings-memory-repo",
                "settings-memory-all",
                "settings-wizard",
                "settings-reset-state",
            ):
                assert app.query_one(f"#{bid}", Button) is not None

    asyncio.run(run())


def test_settings_init_policy_home_writes_file(tmp_path, monkeypatch):
    async def run() -> None:
        home = tmp_path / "home"
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(home))
        app = _app(tmp_path, initial_tab="settings")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button

            app.query_one("#settings-policy-home", Button).press()
            await pilot.pause()
            assert (home / "policy.toml").exists()

    asyncio.run(run())


def test_settings_reset_state_clears(tmp_path, monkeypatch):
    async def run() -> None:
        home = tmp_path / "home"
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(home))
        from frontier_scout.store import setup_state_path, write_setup_state

        write_setup_state({"dismissed_tools": ["foo/bar"]})
        app = _app(tmp_path, initial_tab="settings")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button

            app.query_one("#settings-reset-state", Button).press()
            await pilot.pause()
            state = json.loads(setup_state_path().read_text())
            assert state == {}

    asyncio.run(run())


def test_settings_does_not_crash_on_missing_files(tmp_path, monkeypatch):
    """v1.2 hardening: Settings must render even when policy/state files are
    missing or unreadable."""

    async def run() -> None:
        # No FRONTIER_SCOUT_HOME set explicitly — but tmp_path provides a clean
        # surface. Force a missing setup_state.
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "void"))
        app = _app(tmp_path, initial_tab="settings")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Static

            # All four panel statics must be present, not error rendering.
            for sid in (
                "policy-text",
                "settings-env-text",
                "settings-memory-text",
                "settings-automation-text",
                "settings-system-text",
            ):
                text = str(app.query_one(f"#{sid}", Static).render())
                assert "rendering error" not in text

    asyncio.run(run())
