"""Tests for the clear-scout-memory helpers."""

from __future__ import annotations

from pathlib import Path

from frontier_scout.scout import run_scan
from frontier_scout.store import (
    clear_all_scans,
    clear_scans_for_repo,
    latest_scan,
)


def test_clear_repo_scans(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    # Persist a dry-run scan for tmp_path.
    run_scan(repo=tmp_path, dry_run=True, persist=True)
    latest = latest_scan()
    assert latest is not None
    removed = clear_scans_for_repo(tmp_path)
    assert removed >= 1
    assert latest_scan() is None


def test_clear_all(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    run_scan(repo=tmp_path, dry_run=True, persist=True)
    other = tmp_path / "other"
    other.mkdir()
    run_scan(repo=other, dry_run=True, persist=True)
    removed = clear_all_scans()
    assert removed >= 2
    assert latest_scan() is None


def test_clear_for_unknown_repo_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    # SQLite doesn't exist yet → no rows to remove.
    assert clear_scans_for_repo(tmp_path) == 0
