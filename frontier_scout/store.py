"""Local SQLite store for Frontier Scout."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def home_dir() -> Path:
    return Path(os.environ.get("FRONTIER_SCOUT_HOME", "~/.frontier-scout")).expanduser()


def db_path() -> Path:
    return home_dir() / "db.sqlite"


def init_home() -> Path:
    home = home_dir()
    home.mkdir(parents=True, exist_ok=True)
    init_db(db_path())
    return home


def init_db(path: Path | None = None) -> Path:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                repo TEXT,
                scanned INTEGER DEFAULT 0,
                candidates INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                duration_s REAL DEFAULT 0,
                judge_rating TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                tool_name TEXT NOT NULL,
                verdict TEXT NOT NULL,
                category TEXT,
                risk TEXT,
                fit TEXT,
                source_url TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_verdicts_scan ON verdicts(scan_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_verdicts_tool ON verdicts(tool_name)"
        )
    return path


def save_scan(payload: dict[str, Any], *, repo: str | None = None) -> int:
    path = init_db()
    verdicts = list(payload.get("verdicts") or [])
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO scans (
                created_at, repo, scanned, candidates, cost_usd, duration_s,
                judge_rating, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                repo,
                int(payload.get("scanned") or payload.get("items_scanned") or 0),
                int(payload.get("candidates") or 0),
                float(payload.get("cost_usd") or payload.get("total_cost_usd") or 0),
                float(payload.get("duration_s") or 0),
                payload.get("judge_rating") or payload.get("judge_self_rating"),
                json.dumps(payload),
            ),
        )
        scan_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO verdicts (
                scan_id, tool_name, verdict, category, risk, fit, source_url,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    scan_id,
                    v.get("tool_name", ""),
                    v.get("verdict", ""),
                    v.get("category"),
                    v.get("risk"),
                    v.get("fit"),
                    v.get("source_url"),
                    json.dumps(v),
                )
                for v in verdicts
            ],
        )
    return scan_id


def latest_scan() -> dict[str, Any] | None:
    path = db_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])

