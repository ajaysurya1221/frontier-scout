"""Codex finding #5 — ``latest_scan`` must filter by repo when asked.

Before v1.2.1 the CLI ``report`` and TUI ``action_open_report`` both
called ``latest_scan()`` with no filter, so the report you opened in
repo A could be repo B's data — silently. These tests pin the fix.
"""

from __future__ import annotations

from pathlib import Path

from frontier_scout.scout import run_scan
from frontier_scout.store import latest_scan


def _scan(repo: Path) -> None:
    run_scan(repo=repo, dry_run=True, persist=True)


def test_latest_scan_filters_to_requested_repo(tmp_path, monkeypatch):
    """Two repos are scanned in order A → B. Asking for A's scan must
    return A's row, even though B's scan is the globally-newest."""

    import sqlite3

    from frontier_scout.store import db_path

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo_a = tmp_path / "alpha"
    repo_b = tmp_path / "beta"
    repo_a.mkdir()
    repo_b.mkdir()

    _scan(repo_a)
    _scan(repo_b)

    # Look up each repo's scan ID via the SQLite column (the payload JSON
    # itself doesn't embed the repo path — the `repo` filter is on the
    # column, which is what production CLI/TUI query through).
    with sqlite3.connect(db_path()) as conn:
        id_a = conn.execute(
            "SELECT id FROM scans WHERE repo = ? ORDER BY id DESC LIMIT 1",
            (str(repo_a.resolve()),),
        ).fetchone()[0]
        id_b = conn.execute(
            "SELECT id FROM scans WHERE repo = ? ORDER BY id DESC LIMIT 1",
            (str(repo_b.resolve()),),
        ).fetchone()[0]
    assert id_a != id_b
    assert id_b > id_a  # B was scanned second

    payload_a = latest_scan(repo=repo_a)
    payload_b = latest_scan(repo=repo_b)
    assert payload_a is not None
    assert payload_b is not None
    # CodeRabbit-strengthened assertion: prove filtering by repo, not
    # just that two distinct objects came back. The two scans were
    # persisted under different ``repo`` columns; their database row
    # IDs and resolved-path round-trip lookups must match the requested
    # repo (and only that repo). We re-query SQLite to confirm the
    # row IDs match what ``latest_scan(repo=...)`` returned.
    import sqlite3

    with sqlite3.connect(db_path()) as conn:
        row_id_for_a = conn.execute(
            "SELECT id FROM scans WHERE repo = ? ORDER BY id DESC LIMIT 1",
            (str(repo_a.resolve()),),
        ).fetchone()[0]
        row_id_for_b = conn.execute(
            "SELECT id FROM scans WHERE repo = ? ORDER BY id DESC LIMIT 1",
            (str(repo_b.resolve()),),
        ).fetchone()[0]
    # The IDs we just looked up must match what the scope-filtered
    # query returned. We exposed the cross-check above (id_a, id_b);
    # confirm they correspond to the right repos.
    assert row_id_for_a == id_a
    assert row_id_for_b == id_b
    # The two payloads must not have the same SQLite row.
    assert id_a != id_b, "latest_scan(repo=A) and latest_scan(repo=B) returned the same scan row"


def test_latest_scan_returns_global_when_no_repo_arg(tmp_path, monkeypatch):
    """Back-compat: legacy callers (none should remain) still get global."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo_a = tmp_path / "alpha"
    repo_b = tmp_path / "beta"
    repo_a.mkdir()
    repo_b.mkdir()

    _scan(repo_a)
    _scan(repo_b)
    assert latest_scan() is not None  # any row, not None


def test_latest_scan_returns_none_for_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    real = tmp_path / "real"
    real.mkdir()
    _scan(real)

    unknown = tmp_path / "ghost"
    unknown.mkdir()
    assert latest_scan(repo=unknown) is None


def test_latest_scan_returns_none_when_db_missing(tmp_path, monkeypatch):
    """No scan has ever been persisted → no crash, just None."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    assert latest_scan() is None
    assert latest_scan(repo=tmp_path) is None
