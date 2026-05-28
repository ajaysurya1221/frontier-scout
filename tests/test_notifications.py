"""Tests for the notifications subsystem."""

from __future__ import annotations

from pathlib import Path

from frontier_scout.notifications import (
    clear_all,
    list_notifications,
    mark_read,
    notify_new_verdicts,
    unread_count,
    write_notification,
)
from frontier_scout.scheduling import Schedule


def test_write_and_list_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    path = write_notification(
        repo="/tmp/repo",
        schedule_id="abc",
        new_verdicts=[{"tool_name": "openai/foo", "verdict": "adopt"}],
        result_dir=Path("/tmp/result"),
    )
    assert path is not None
    items = list_notifications()
    assert len(items) == 1
    assert items[0]["schedule_id"] == "abc"
    assert items[0]["read"] is False
    assert unread_count() == 1


def test_write_empty_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    assert (
        write_notification(
            repo="/tmp/repo",
            schedule_id="abc",
            new_verdicts=[],
            result_dir=Path("/tmp/result"),
        )
        is None
    )


def test_mark_read(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    path = write_notification(
        repo="/tmp/repo",
        schedule_id="abc",
        new_verdicts=[{"tool_name": "openai/foo", "verdict": "adopt"}],
        result_dir=Path("/tmp/result"),
    )
    mark_read(str(path))
    items = list_notifications()
    assert items[0]["read"] is True
    assert unread_count() == 0


def test_clear_all(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    write_notification(
        repo="/tmp/repo",
        schedule_id="x",
        new_verdicts=[{"tool_name": "foo", "verdict": "adopt"}],
        result_dir=Path("/tmp"),
    )
    write_notification(
        repo="/tmp/repo",
        schedule_id="y",
        new_verdicts=[{"tool_name": "bar", "verdict": "trial"}],
        result_dir=Path("/tmp"),
    )
    assert len(list_notifications()) == 2
    removed = clear_all()
    assert removed == 2
    assert list_notifications() == []


def test_notify_skips_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    sched = Schedule(id="x", repo=str(tmp_path), cron_expr="@daily", notification="disabled")
    result = notify_new_verdicts(
        schedule=sched,
        verdicts=[{"tool_name": "foo", "verdict": "adopt"}],
        result_dir=tmp_path,
    )
    assert result is None
