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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL UNIQUE,
                category TEXT,
                primary_url TEXT,
                package_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                category TEXT,
                fit TEXT,
                risk TEXT,
                source_trust TEXT,
                score INTEGER DEFAULT 0,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permission_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                evidence_source TEXT,
                confidence TEXT,
                dangerous_flags_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trial_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                requested_action TEXT,
                status TEXT NOT NULL,
                decision TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trial_id INTEGER NOT NULL REFERENCES trial_runs(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                runtime TEXT,
                status TEXT,
                exit_code INTEGER,
                duration_s REAL DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                transcript_path TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policy_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                trial_id INTEGER REFERENCES trial_runs(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                severity TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS adoption_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                decision TEXT NOT NULL,
                approver_label TEXT,
                rationale TEXT,
                revisit_after TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policy_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER REFERENCES tools(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                expires_at TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(tool_name)",
            "CREATE INDEX IF NOT EXISTS idx_evaluations_tool ON evaluations(tool_id)",
            "CREATE INDEX IF NOT EXISTS idx_manifests_tool ON permission_manifests(tool_id)",
            "CREATE INDEX IF NOT EXISTS idx_trials_tool ON trial_runs(tool_id)",
            "CREATE INDEX IF NOT EXISTS idx_lab_trial ON lab_results(trial_id)",
            "CREATE INDEX IF NOT EXISTS idx_findings_tool ON policy_findings(tool_id)",
        ):
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (1, _now()),
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


def upsert_tool(
    tool_name: str,
    *,
    category: str | None = None,
    primary_url: str | None = None,
    package_name: str | None = None,
) -> int:
    init_db()
    now = _now()
    with sqlite3.connect(db_path()) as conn:
        row = conn.execute("SELECT id FROM tools WHERE tool_name = ?", (tool_name,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE tools
                SET category = COALESCE(?, category),
                    primary_url = COALESCE(?, primary_url),
                    package_name = COALESCE(?, package_name),
                    updated_at = ?
                WHERE id = ?
                """,
                (category, primary_url, package_name, now, row[0]),
            )
            return int(row[0])
        cur = conn.execute(
            """
            INSERT INTO tools(tool_name, category, primary_url, package_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tool_name, category, primary_url, package_name, now, now),
        )
        return int(cur.lastrowid)


def save_evaluation(evaluation: Any) -> int:
    payload = _dump_model(evaluation)
    tool_id = upsert_tool(
        payload["tool_name"],
        category=payload.get("category"),
        primary_url=payload.get("source_url"),
        package_name=payload.get("package"),
    )
    with sqlite3.connect(init_db()) as conn:
        conn.execute(
            """
            INSERT INTO evaluations(
                tool_id, created_at, source_url, category, fit, risk,
                source_trust, score, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_id,
                _now(),
                payload.get("source_url", ""),
                payload.get("category"),
                payload.get("fit"),
                payload.get("risk"),
                payload.get("source_trust"),
                int(payload.get("score") or 0),
                json.dumps(payload),
            ),
        )
    return tool_id


def save_permission_manifest(tool_id: int, manifest: Any) -> int:
    payload = _dump_model(manifest)
    with sqlite3.connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO permission_manifests(
                tool_id, created_at, evidence_source, confidence,
                dangerous_flags_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tool_id,
                _now(),
                payload.get("evidence_source"),
                payload.get("confidence"),
                json.dumps(payload.get("dangerous_flags") or []),
                json.dumps(payload),
            ),
        )
        return int(cur.lastrowid)


def create_trial_run(tool_id: int, *, requested_action: str) -> int:
    with sqlite3.connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO trial_runs(tool_id, created_at, requested_action, status, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tool_id, _now(), requested_action, "running", "{}"),
        )
        return int(cur.lastrowid)


def finish_trial_run(trial_id: int, *, status: str, decision: str | None = None) -> None:
    with sqlite3.connect(init_db()) as conn:
        conn.execute(
            """
            UPDATE trial_runs
            SET completed_at = ?, status = ?, decision = ?
            WHERE id = ?
            """,
            (_now(), status, decision, trial_id),
        )


def save_lab_result(trial_id: int, result: dict[str, Any]) -> int:
    with sqlite3.connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO lab_results(
                trial_id, created_at, runtime, status, exit_code, duration_s,
                cost_usd, transcript_path, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trial_id,
                _now(),
                result.get("runtime"),
                result.get("status"),
                result.get("exit_code"),
                float(result.get("duration_s") or 0),
                float(result.get("cost_usd") or 0),
                result.get("transcript_path"),
                json.dumps(result),
            ),
        )
        return int(cur.lastrowid)


def save_policy_findings(
    tool_id: int,
    findings: list[Any],
    *,
    trial_id: int | None = None,
) -> None:
    if not findings:
        return
    rows = []
    for finding in findings:
        payload = _dump_model(finding)
        rows.append(
            (
                tool_id,
                trial_id,
                _now(),
                payload.get("severity", "info"),
                payload.get("rule_id", ""),
                payload.get("message", ""),
                json.dumps(payload),
            )
        )
    with sqlite3.connect(init_db()) as conn:
        conn.executemany(
            """
            INSERT INTO policy_findings(
                tool_id, trial_id, created_at, severity, rule_id, message, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def latest_trial_for_tool(tool_name: str) -> dict[str, Any] | None:
    path = db_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT tr.*, t.tool_name
            FROM trial_runs tr
            JOIN tools t ON t.id = tr.tool_id
            WHERE t.tool_name = ?
            ORDER BY tr.id DESC
            LIMIT 1
            """,
            (tool_name,),
        ).fetchone()
        if row is None:
            return None
        lab = conn.execute(
            """
            SELECT payload_json FROM lab_results
            WHERE trial_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (row["id"],),
        ).fetchone()
    out = dict(row)
    out["lab_result"] = json.loads(lab[0]) if lab else None
    return out


def list_guard_records() -> list[dict[str, Any]]:
    path = db_path()
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                t.id AS tool_id,
                t.tool_name,
                pm.dangerous_flags_json,
                pm.payload_json AS manifest_json,
                (
                    SELECT status FROM trial_runs tr
                    WHERE tr.tool_id = t.id
                    ORDER BY tr.id DESC LIMIT 1
                ) AS latest_trial_status,
                (
                    SELECT decision FROM trial_runs tr
                    WHERE tr.tool_id = t.id
                    ORDER BY tr.id DESC LIMIT 1
                ) AS latest_decision
            FROM tools t
            JOIN permission_manifests pm ON pm.id = (
                SELECT id FROM permission_manifests pm2
                WHERE pm2.tool_id = t.id
                ORDER BY pm2.id DESC LIMIT 1
            )
            ORDER BY t.tool_name
            """
        ).fetchall()
    records = []
    for row in rows:
        item = dict(row)
        item["dangerous_flags"] = json.loads(item.pop("dangerous_flags_json") or "[]")
        item["manifest"] = json.loads(item.pop("manifest_json") or "{}")
        records.append(item)
    return records


def list_trial_summaries(limit: int = 20) -> list[dict[str, Any]]:
    path = db_path()
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT tr.*, t.tool_name, t.primary_url
            FROM trial_runs tr
            JOIN tools t ON t.id = tr.tool_id
            ORDER BY tr.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
