"""Tab-mount and one-action smoke tests for the v1 Mission Control."""

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

    return SetupApp(diagnostics, show_splash=False, initial_tab=initial_tab)


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------


def test_scout_tab_auto_populates(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import DataTable

            for _ in range(50):
                await pilot.pause()
                table = app.query_one("#scout-table", DataTable)
                if table.row_count > 0:
                    break
            assert table.row_count >= 1

    asyncio.run(run())


def test_scout_tab_dismiss_persists(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import Button, DataTable

            for _ in range(50):
                await pilot.pause()
                if app.query_one("#scout-table", DataTable).row_count > 0:
                    break
            table = app.query_one("#scout-table", DataTable)
            table.cursor_coordinate = (0, 0)
            await pilot.pause()
            app.query_one("#scout-dismiss", Button).press()
            await pilot.pause()

            from frontier_scout.store import setup_state_path

            state = json.loads(setup_state_path().read_text())
            assert state.get("dismissed_tools")

    asyncio.run(run())


def test_scout_live_scout_gated_without_api_key(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        app = _app(tmp_path)
        async with app.run_test(size=(140, 36)) as pilot:
            from textual.widgets import DataTable

            for _ in range(50):
                await pilot.pause()
                if app.query_one("#scout-table", DataTable).row_count > 0:
                    break
            captured: list[str] = []
            original = app.log_event

            def capture(message: str, tone: str = "ok") -> None:
                captured.append(message)
                original(message, tone)

            monkeypatch.setattr(app, "log_event", capture)
            # Invoke the gated action directly — the binding only dispatches
            # when the ScoutTab has focus, which isn't guaranteed in pilot.
            from frontier_scout.tui.tabs.scout_tab import ScoutTab

            scout_tab = app.query_one(ScoutTab)
            scout_tab.action_live_scout()
            await pilot.pause()
            assert any(
                "requires" in msg.lower() or "skipped" in msg.lower() for msg in captured
            )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------


def test_trials_tab_lists_existing_trials(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="trials")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.query_one("#trials-table", DataTable)
            # Empty store renders the placeholder row.
            assert table.row_count >= 1

    asyncio.run(run())


def test_trials_tab_new_trial_form_toggles(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="trials")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.containers import Vertical
            from textual.widgets import Button

            form = app.query_one("#trials-form", Vertical)
            assert "hidden" in form.classes
            app.query_one("#trials-new", Button).press()
            await pilot.pause()
            assert "hidden" not in form.classes

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


def test_receipts_tab_mounts_table(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="receipts")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.query_one("#receipts-table", DataTable)
            assert table.row_count >= 1  # placeholder row when no receipts yet

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


def test_guard_tab_run_renders_summary(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="guard")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button, Static

            app.query_one("#guard-run", Button).press()
            for _ in range(60):
                await pilot.pause()
                summary = str(app.query_one("#guard-summary", Static).render())
                if "Clean" in summary or "finding" in summary:
                    break
            else:
                raise AssertionError("guard summary did not update")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def test_reports_tab_demo_writes_html(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        monkeypatch.chdir(tmp_path)
        app = _app(tmp_path, initial_tab="reports")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button

            app.query_one("#reports-demo", Button).press()
            await pilot.pause()
            html = tmp_path / "demo" / "briefing.html"
            assert html.exists()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Packs
# ---------------------------------------------------------------------------


def test_packs_tab_lists_default_packs(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="packs")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable

            table = app.query_one("#packs-table", DataTable)
            assert table.row_count >= 5  # default packs registry has several entries

    asyncio.run(run())


def test_packs_tab_discover_requires_confirm(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="packs")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button

            captured: list[str] = []
            original = app.log_event

            def capture(message: str, tone: str = "ok") -> None:
                captured.append(message)
                original(message, tone)

            monkeypatch.setattr(app, "log_event", capture)
            app.query_one("#packs-discover", Button).press()
            await pilot.pause()
            assert any("Press again" in msg or "confirm" in msg.lower() for msg in captured)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Deps
# ---------------------------------------------------------------------------


def test_deps_tab_run_renders_table(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="deps")

        from frontier_scout.tui.tabs.deps_tab import DepsTab

        def fake_scan(repo):
            return {
                "findings": [
                    {
                        "verdict": "trial",
                        "package_name": "fastapi",
                        "from_version": "0.110",
                        "to_version": "0.115",
                        "classification": "minor",
                    }
                ]
            }

        monkeypatch.setattr(
            "frontier_scout.dependencies.run_dependency_scan", fake_scan
        )
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button, DataTable

            app.query_one("#deps-run", Button).press()
            for _ in range(40):
                await pilot.pause()
                table = app.query_one("#deps-table", DataTable)
                if table.row_count >= 1:
                    break
            assert table.row_count >= 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


def test_incident_tab_run_demo_populates_paths(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        app = _app(tmp_path, initial_tab="incident")

        def fake_run(**kwargs):
            return {
                "run_id": "fake-run",
                "answer_path": "/tmp/answer.md",
                "trace_path": "/tmp/trace.jsonl",
                "audit_path": "/tmp/audit.jsonl",
                "eval_path": "/tmp/eval.json",
                "eval": {"score": 1.0},
                "interrupted": False,
            }

        monkeypatch.setattr(
            "frontier_scout.platform.incident_change_scout.workflow.run_incident_demo",
            fake_run,
        )
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            from textual.widgets import Button, Static

            app.query_one("#incident-run", Button).press()
            for _ in range(40):
                await pilot.pause()
                text = str(app.query_one("#incident-artifacts", Static).render())
                if "fake-run" in text:
                    break
            else:
                raise AssertionError("artifacts did not populate")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_tab_init_policy_home(tmp_path, monkeypatch):
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


def test_settings_tab_reset_state(tmp_path, monkeypatch):
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
