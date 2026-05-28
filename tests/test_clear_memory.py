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


# ---------------------------------------------------------------------------
# v1.2.1 — Codex finding #4: cascade integrity
# ---------------------------------------------------------------------------


def _verdict_count_for_repo(repo_path: str) -> int:
    import sqlite3

    from frontier_scout.store import db_path

    with sqlite3.connect(db_path()) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM verdicts WHERE scan_id IN "
            "(SELECT id FROM scans WHERE repo = ?)",
            (repo_path,),
        )
        return int(cur.fetchone()[0])


def _total_verdict_count() -> int:
    import sqlite3

    from frontier_scout.store import db_path

    with sqlite3.connect(db_path()) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM verdicts")
        return int(cur.fetchone()[0])


def test_clear_scans_for_repo_leaves_no_orphan_verdicts(tmp_path, monkeypatch):
    """Before v1.2.1, ``clear_scans_for_repo`` only deleted from ``scans``
    and SQLite's ON DELETE CASCADE was a lie because foreign keys were
    not enabled. Now both rows go."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    run_scan(repo=tmp_path, dry_run=True, persist=True)
    target = str(tmp_path.resolve())
    assert _verdict_count_for_repo(target) > 0

    clear_scans_for_repo(tmp_path)
    assert _verdict_count_for_repo(target) == 0


def test_clear_all_scans_empties_verdicts(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    run_scan(repo=tmp_path, dry_run=True, persist=True)
    other = tmp_path / "other"
    other.mkdir()
    run_scan(repo=other, dry_run=True, persist=True)
    assert _total_verdict_count() > 0

    clear_all_scans()
    assert _total_verdict_count() == 0


def test_foreign_keys_pragma_is_enabled():
    """``_connect`` turns on foreign key enforcement so cascades actually fire."""

    from frontier_scout.store import _connect, db_path, init_db

    init_db()
    with _connect(db_path()) as conn:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
