"""Tests for the cron-based scheduling subsystem."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from frontier_scout.scheduling import (
    Schedule,
    add_schedule,
    crontab_line,
    install_cron_runner,
    is_due,
    is_valid_cron_expr,
    load_schedules,
    normalise_cron_expr,
    record_run,
    remove_schedule,
    save_schedules,
    schedules_path,
)


def test_normalise_cron_macros():
    assert normalise_cron_expr("@daily") == "0 0 * * *"
    assert normalise_cron_expr("@hourly") == "0 * * * *"
    assert normalise_cron_expr("0 9 * * 1") == "0 9 * * 1"


def test_is_valid_cron_macros_and_expressions():
    assert is_valid_cron_expr("@daily")
    assert is_valid_cron_expr("0 9 * * 1")
    assert not is_valid_cron_expr("not-a-cron")


def test_add_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = add_schedule(tmp_path, cron_expr="@daily", notification="file")
    schedules = load_schedules()
    assert len(schedules) == 1
    assert schedules[0].id == sched.id
    assert schedules[0].repo == str(tmp_path.resolve())
    assert schedules[0].cron_expr == "@daily"


def test_remove_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = add_schedule(tmp_path, cron_expr="@hourly")
    assert remove_schedule(sched.id) is True
    assert remove_schedule(sched.id) is False
    assert load_schedules() == []


def test_install_cron_runner_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    first = install_cron_runner()
    second = install_cron_runner()
    assert first == second
    assert first.exists()
    assert first.stat().st_mode & 0o111 != 0


def test_crontab_line_includes_runner_path(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    install_cron_runner()
    assert "cron-runner.sh" in crontab_line()


def test_is_due_never_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = add_schedule(tmp_path, cron_expr="@hourly")
    assert is_due(sched)


def test_is_due_recent_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = add_schedule(tmp_path, cron_expr="@daily")
    now = datetime.now(tz=timezone.utc)
    # Record a run that happened seconds ago; @daily fires at midnight so it
    # should NOT be due again until tomorrow's midnight.
    record_run(sched, result_dir=tmp_path, verdict_count=0, now=now)
    reloaded = load_schedules()[0]
    assert not is_due(reloaded, now=now)


def test_disabled_schedule_is_not_due(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = add_schedule(tmp_path, cron_expr="@hourly")
    sched.disabled = True
    save_schedules([sched])
    assert not is_due(sched)
