"""P1-1: the ``sanctioned`` pack-candidate state + its CHECK-widening migration.

TDD (data-model behavior): a fresh DB must accept ``state='sanctioned'``; ``init_db`` must be
idempotent and stamp schema version 7; and a *legacy* DB created with the old four-value CHECK
must be migrated in place, preserving its existing rows.
"""

import sqlite3

from frontier_scout import store
from frontier_scout.packs import PackCandidate

_LEGACY_SCHEMA = """
CREATE TABLE tools (id INTEGER PRIMARY KEY AUTOINCREMENT, tool_name TEXT UNIQUE NOT NULL);
CREATE TABLE packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL, description TEXT, definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE pack_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
    tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (state IN ('candidate','watched','core','retired')),
    freshness_score REAL NOT NULL, consensus_score REAL NOT NULL,
    state_changed_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
    UNIQUE(pack_id, tool_id));
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
INSERT INTO tools(id, tool_name) VALUES (1, 'legacy-server'), (2, 'new-server');
INSERT INTO packs(id, slug, display_name, description, definition_json, created_at, updated_at)
    VALUES (1, 'mcp', 'MCP', 'x', '{}', '2026-01-01', '2026-01-01');
INSERT INTO pack_candidates(pack_id, tool_id, state, freshness_score, consensus_score,
    state_changed_at, evidence_json) VALUES (1, 1, 'core', 1.0, 1.0, '2026-01-01', '[]');
"""


def test_save_pack_candidate_accepts_sanctioned(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(pack_slug="mcp", tool_name="acme-mcp", state="sanctioned")
    )
    states = {r["tool_name"]: r["state"] for r in store.list_pack_candidates("mcp")}
    assert states.get("acme-mcp") == "sanctioned"


def test_init_db_idempotent_and_stamps_v7(tmp_path):
    path = tmp_path / "db.sqlite"
    store.init_db(path)
    store.init_db(path)  # second run must not raise
    conn = sqlite3.connect(path)
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()]
    conn.close()
    assert 7 in versions
    assert versions.count(7) == 1


def test_legacy_pack_candidates_migrated_preserving_rows(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(_LEGACY_SCHEMA)
    conn.commit()
    conn.close()

    store.init_db(path)  # runs the CHECK-widening migration

    conn = sqlite3.connect(path)
    legacy = conn.execute("SELECT state FROM pack_candidates WHERE tool_id = 1").fetchone()
    assert legacy is not None and legacy[0] == "core", "legacy row must be preserved"
    # Under the old CHECK this INSERT raises IntegrityError.
    conn.execute(
        "INSERT INTO pack_candidates(pack_id, tool_id, state, freshness_score, "
        "consensus_score, state_changed_at, evidence_json) "
        "VALUES (1, 2, 'sanctioned', 0.0, 0.0, '2026-01-02', '[]')"
    )
    conn.commit()
    got = conn.execute("SELECT state FROM pack_candidates WHERE tool_id = 2").fetchone()[0]
    assert got == "sanctioned"
    conn.close()
