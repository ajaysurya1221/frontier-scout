"""Tests for the setup wizard (Textual app + headless mode)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from frontier_scout.wizard.config import is_onboarded, load_config
from frontier_scout.wizard.headless import run_headless


def test_headless_adhoc(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    result = run_headless(mode="adhoc", llm="local")
    assert result["mode"] == "adhoc"
    cfg = load_config()
    assert cfg["llm"]["preferred"] == "local"
    assert cfg["setup"]["mode"] == "adhoc"
    assert is_onboarded()


def test_headless_automation(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    result = run_headless(
        mode="automation",
        llm="ollama",
        repos=[str(repo)],
        cron_expr="@hourly",
        notification="file",
    )
    assert result["mode"] == "automation"
    assert len(result["schedules"]) == 1
    assert result["schedules"][0]["cron_expr"] == "@hourly"
    assert "cron-runner.sh" in result["crontab_line"]


def test_headless_automation_invalid_cron(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        run_headless(mode="automation", repos=[str(repo)], cron_expr="not-a-cron")
    except ValueError as exc:
        assert "invalid cron" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for invalid cron expression")


def test_headless_automation_requires_repos(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    try:
        run_headless(mode="automation", cron_expr="@daily")
    except ValueError as exc:
        assert "repo" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected ValueError when no repos provided")


def test_wizard_app_lands_on_welcome(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        from frontier_scout.wizard.app import WelcomeScreen, WizardApp

        app = WizardApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WelcomeScreen)

    asyncio.run(run())


def test_wizard_adhoc_flow_completes(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        from textual.widgets import Button

        from frontier_scout.wizard.app import (
            AdhocStepScreen,
            LLMStepScreen,
            ModeStepScreen,
            WizardApp,
        )

        app = WizardApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#wiz-welcome-continue", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, LLMStepScreen)
            app.screen.query_one("#pick-local", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, ModeStepScreen)
            app.screen.query_one("#mode-adhoc", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, AdhocStepScreen)
        # Wizard completed; setup state should be persisted as onboarded.
        assert is_onboarded()

    asyncio.run(run())
