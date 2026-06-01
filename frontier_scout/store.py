"""Local SQLite store for Frontier Scout."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
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


def _connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key constraints enforced.

    Without ``PRAGMA foreign_keys = ON`` SQLite silently ignores every
    ``ON DELETE CASCADE`` declaration in the schema, so deleting a scan
    leaves orphan verdicts (and so on for every child table). Closes
    Codex review finding #4.
    """

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> Path:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repo_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT NOT NULL,
                repo_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scout_graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pack_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                state TEXT NOT NULL CHECK (state IN ('candidate','watched','core','retired')),
                freshness_score REAL NOT NULL,
                consensus_score REAL NOT NULL,
                state_changed_at TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                UNIQUE(pack_id, tool_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dependency_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id TEXT NOT NULL,
                ecosystem TEXT NOT NULL,
                package_name TEXT NOT NULL,
                from_version TEXT NOT NULL,
                to_version TEXT NOT NULL,
                classification TEXT NOT NULL CHECK (
                    classification IN ('security','hardening','breaking','feature','noise')
                ),
                classifier_confidence REAL NOT NULL,
                advisory_ids_json TEXT,
                evidence_quotes_json TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pack_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_slug TEXT NOT NULL,
                tool_identifier TEXT NOT NULL,
                override TEXT NOT NULL CHECK (override IN ('include','exclude','pin','suppress','retire')),
                reason TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dep_intel_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL CHECK (source IN ('osv','pypi','npm','github_release')),
                cache_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                ttl_seconds INTEGER NOT NULL,
                UNIQUE(source, cache_key)
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
            "CREATE INDEX IF NOT EXISTS idx_profiles_repo ON repo_profiles(repo_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_source ON scout_graph_edges(source_type, source_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_target ON scout_graph_edges(target_type, target_id)",
            "CREATE INDEX IF NOT EXISTS idx_pack_candidates_pack ON pack_candidates(pack_id)",
            "CREATE INDEX IF NOT EXISTS idx_dep_findings_repo ON dependency_findings(repo_id)",
            "CREATE INDEX IF NOT EXISTS idx_dep_cache_key ON dep_intel_cache(source, cache_key)",
        ):
            conn.execute(statement)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (1, _now()),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (5, _now()),
        )
        # v1.2.1 (Codex review #4): every future _connect() turns foreign keys
        # on, so cascades work and clear-history is honest. No schema change —
        # we record the milestone so a future migration can detect upgrade
        # state.
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (6, _now()),
        )
    return path


def save_scan(payload: dict[str, Any], *, repo: str | None = None) -> int:
    path = init_db()
    verdicts = list(payload.get("verdicts") or [])
    with _connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO scans (
                created_at, repo, scanned, candidates, cost_usd, duration_s,
                judge_rating, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
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


def latest_scan(repo: Path | str | None = None) -> dict[str, Any] | None:
    """Return the most recent scan payload.

    With no ``repo`` argument, returns the globally newest scan (legacy
    behaviour). With ``repo`` set, scopes to that resolved path — fixes
    Codex finding #5 where TUI / CLI ``report`` happily rendered another
    repo's data because there was no filter.
    """

    path = db_path()
    if not path.exists():
        return None
    with _connect(path) as conn:
        if repo is None:
            row = conn.execute(
                "SELECT payload_json FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            resolved = str(Path(str(repo)).expanduser().resolve())
            row = conn.execute(
                "SELECT payload_json FROM scans WHERE repo = ? "
                "ORDER BY id DESC LIMIT 1",
                (resolved,),
            ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def save_repo_profile(profile: Any) -> int:
    payload = _dump_model(profile)
    with _connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO repo_profiles(repo_id, repo_path, created_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                payload.get("repo_id", ""),
                payload.get("repo", ""),
                _now(),
                json.dumps(payload),
            ),
        )
        profile_id = int(cur.lastrowid)
        rows = []
        for key in (
            "languages",
            "frameworks",
            "package_managers",
            "ci",
            "containers",
            "agent_configs",
            "ai_tooling",
            "risk_flags",
        ):
            for value in payload.get(key) or []:
                rows.append(
                    (
                        _now(),
                        "repo_profile",
                        payload.get("repo_id", ""),
                        f"has_{key[:-1] if key.endswith('s') else key}",
                        "signal",
                        str(value),
                        json.dumps({"profile_id": profile_id, "field": key}),
                    )
                )
        for dependency in payload.get("dependencies") or []:
            rows.append(
                (
                    _now(),
                    "repo_profile",
                    payload.get("repo_id", ""),
                    "uses_dependency",
                    str(dependency.get("ecosystem") or "dependency"),
                    str(dependency.get("name") or ""),
                    json.dumps({"profile_id": profile_id, "dependency": dependency}),
                )
            )
        if rows:
            conn.executemany(
                """
                INSERT INTO scout_graph_edges(
                    created_at, source_type, source_id, relation,
                    target_type, target_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return profile_id


def latest_repo_profile(repo: str | None = None) -> dict[str, Any] | None:
    path = db_path()
    if not path.exists():
        return None
    query = "SELECT payload_json FROM repo_profiles"
    params: tuple[Any, ...] = ()
    if repo:
        query += " WHERE repo_path = ?"
        params = (repo,)
    query += " ORDER BY id DESC LIMIT 1"
    with _connect(path) as conn:
        row = conn.execute(query, params).fetchone()
    return json.loads(row[0]) if row else None


def find_latest_verdict(tool: str) -> dict[str, Any] | None:
    path = init_db()
    if not path.exists():
        return None
    needle = tool.lower()
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT payload_json FROM verdicts
            ORDER BY id DESC
            """
        ).fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        haystacks = [
            str(payload.get("tool_name", "")).lower(),
            str(payload.get("source_url", "")).lower(),
        ]
        if any(needle in haystack or haystack in needle for haystack in haystacks if haystack):
            return payload
    return None


def upsert_tool(
    tool_name: str,
    *,
    category: str | None = None,
    primary_url: str | None = None,
    package_name: str | None = None,
) -> int:
    init_db()
    now = _now()
    with _connect(db_path()) as conn:
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
    with _connect(init_db()) as conn:
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
    with _connect(init_db()) as conn:
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
    with _connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO trial_runs(tool_id, created_at, requested_action, status, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tool_id, _now(), requested_action, "running", "{}"),
        )
        return int(cur.lastrowid)


def finish_trial_run(trial_id: int, *, status: str, decision: str | None = None) -> None:
    with _connect(init_db()) as conn:
        conn.execute(
            """
            UPDATE trial_runs
            SET completed_at = ?, status = ?, decision = ?
            WHERE id = ?
            """,
            (_now(), status, decision, trial_id),
        )


def save_lab_result(trial_id: int, result: dict[str, Any]) -> int:
    with _connect(init_db()) as conn:
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
    with _connect(init_db()) as conn:
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
    with _connect(path) as conn:
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
    with _connect(path) as conn:
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
            LEFT JOIN permission_manifests pm ON pm.id = (
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
        # LEFT JOIN: a tool with no stored manifest yields NULL manifest_json.
        # Surface that explicitly so guard can fail CLOSED (a missing manifest
        # means the capability surface was never captured — not that it's safe),
        # matching evaluate_policy's ``capability.missing`` HOLD behaviour.
        item["manifest_missing"] = item.get("manifest_json") is None
        item["dangerous_flags"] = json.loads(item.pop("dangerous_flags_json") or "[]")
        item["manifest"] = json.loads(item.pop("manifest_json") or "{}")
        records.append(item)
    return records


def list_trial_summaries(limit: int = 20) -> list[dict[str, Any]]:
    path = db_path()
    if not path.exists():
        return []
    with _connect(path) as conn:
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


def save_packs(packs: list[Any]) -> None:
    rows = []
    now = _now()
    for pack in packs:
        payload = _dump_model(pack)
        rows.append(
            (
                payload["slug"],
                payload["display_name"],
                payload.get("description"),
                json.dumps(payload),
                now,
                now,
            )
        )
    with _connect(init_db()) as conn:
        conn.executemany(
            """
            INSERT INTO packs(slug, display_name, description, definition_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                definition_json = excluded.definition_json,
                updated_at = excluded.updated_at
            """,
            rows,
        )


def list_packs() -> list[dict[str, Any]]:
    save_builtin_packs_if_empty()
    path = init_db()
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM packs ORDER BY slug").fetchall()
    return [dict(row) | {"definition": json.loads(row["definition_json"])} for row in rows]


def get_pack(slug: str) -> dict[str, Any] | None:
    save_builtin_packs_if_empty()
    with _connect(init_db()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM packs WHERE slug = ?", (slug,)).fetchone()
    return dict(row) | {"definition": json.loads(row["definition_json"])} if row else None


def save_builtin_packs_if_empty() -> None:
    from .packs import default_packs

    path = init_db()
    with _connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM packs").fetchone()
    if row and int(row[0]) > 0:
        return
    save_packs(list(default_packs().values()))


def save_pack_candidate(candidate: Any) -> int:
    from .packs import default_packs

    payload = _dump_model(candidate)
    save_builtin_packs_if_empty()
    pack = get_pack(payload["pack_slug"])
    if not pack:
        pack_def = default_packs()[payload["pack_slug"]]
        save_packs([pack_def])
        pack = get_pack(payload["pack_slug"])
    tool_id = upsert_tool(payload["tool_name"])
    evidence_json = json.dumps(payload.get("evidence") or [])
    with _connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO pack_candidates(
                pack_id, tool_id, state, freshness_score, consensus_score,
                state_changed_at, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pack_id, tool_id) DO UPDATE SET
                state = excluded.state,
                freshness_score = excluded.freshness_score,
                consensus_score = excluded.consensus_score,
                state_changed_at = excluded.state_changed_at,
                evidence_json = excluded.evidence_json
            """,
            (
                int(pack["id"]),
                tool_id,
                payload.get("state", "candidate"),
                float(payload.get("freshness_score") or 0),
                float(payload.get("consensus_score") or 0),
                _now(),
                evidence_json,
            ),
        )
        return int(cur.lastrowid or tool_id)


def list_pack_candidates(pack_slug: str | None = None) -> list[dict[str, Any]]:
    save_builtin_packs_if_empty()
    query = """
        SELECT pc.*, p.slug AS pack_slug, t.tool_name
        FROM pack_candidates pc
        JOIN packs p ON p.id = pc.pack_id
        JOIN tools t ON t.id = pc.tool_id
    """
    params: tuple[Any, ...] = ()
    if pack_slug:
        query += " WHERE p.slug = ?"
        params = (pack_slug,)
    query += " ORDER BY p.slug, t.tool_name"
    with _connect(init_db()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        out.append(item)
    return out


def save_dependency_finding(finding: Any) -> int:
    payload = _dump_model(finding)
    with _connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO dependency_findings(
                repo_id, ecosystem, package_name, from_version, to_version,
                classification, classifier_confidence, advisory_ids_json,
                evidence_quotes_json, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["repo_id"],
                payload["ecosystem"],
                payload["package_name"],
                payload["from_version"],
                payload["to_version"],
                payload["classification"],
                float(payload.get("classifier_confidence") or 0),
                json.dumps(payload.get("advisory_ids") or []),
                json.dumps(payload.get("evidence_quotes") or []),
                _now(),
                json.dumps(payload),
            ),
        )
        return int(cur.lastrowid)


def list_dependency_findings(repo_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM dependency_findings"
    params: tuple[Any, ...] = ()
    if repo_id:
        query += " WHERE repo_id = ?"
        params = (repo_id,)
    query += " ORDER BY id DESC"
    with _connect(init_db()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["advisory_ids"] = json.loads(item.pop("advisory_ids_json") or "[]")
        item["evidence_quotes"] = json.loads(item.pop("evidence_quotes_json") or "[]")
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def get_dep_cache(source: str, cache_key: str) -> dict[str, Any] | None:
    with _connect(init_db()) as conn:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, ttl_seconds
            FROM dep_intel_cache
            WHERE source = ? AND cache_key = ?
            """,
            (source, cache_key),
        ).fetchone()
    if not row:
        return None
    fetched_at = datetime.fromisoformat(row[1])
    age = (datetime.now(UTC) - fetched_at).total_seconds()
    if age > int(row[2]):
        return None
    return json.loads(row[0])


def save_dep_cache(source: str, cache_key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
    with _connect(init_db()) as conn:
        conn.execute(
            """
            INSERT INTO dep_intel_cache(source, cache_key, payload_json, fetched_at, ttl_seconds)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at,
                ttl_seconds = excluded.ttl_seconds
            """,
            (source, cache_key, json.dumps(payload), _now(), int(ttl_seconds)),
        )


def save_pack_override(
    pack_slug: str,
    tool_identifier: str,
    override: str,
    *,
    reason: str | None = None,
    expires_at: str | None = None,
) -> int:
    with _connect(init_db()) as conn:
        cur = conn.execute(
            """
            INSERT INTO pack_overrides(pack_slug, tool_identifier, override, reason, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pack_slug, tool_identifier, override, reason, expires_at, _now()),
        )
        return int(cur.lastrowid)


def clear_scans_for_repo(repo: Path | str) -> int:
    """Delete every stored scan + verdict for ``repo``. Returns the number of
    scan rows removed. Idempotent.

    Belt-and-braces: explicitly deletes dependent ``verdicts`` rows before
    deleting the parent ``scans`` rows, so the result is correct whether
    or not foreign-key enforcement is enabled at runtime (which it is, as
    of v1.2.1 / Codex review finding #4).
    """

    path = db_path()
    if not path.exists():
        return 0
    target = str(Path(str(repo)).expanduser().resolve())
    with _connect(path) as conn:
        conn.execute(
            "DELETE FROM verdicts WHERE scan_id IN ("
            "  SELECT id FROM scans WHERE repo = ?"
            ")",
            (target,),
        )
        cur = conn.execute("DELETE FROM scans WHERE repo = ?", (target,))
        return cur.rowcount or 0


def clear_all_scans() -> int:
    """Delete every stored scan + verdict. Returns the number of rows removed.

    See ``clear_scans_for_repo`` for the belt-and-braces note.
    """

    path = db_path()
    if not path.exists():
        return 0
    with _connect(path) as conn:
        conn.execute("DELETE FROM verdicts")
        cur = conn.execute("DELETE FROM scans")
        return cur.rowcount or 0


def previous_scan_verdicts(*, repo: str) -> list[dict[str, Any]]:
    """Return the previous-to-latest scan's verdicts for ``repo``. Used by the
    notifications diff."""

    path = db_path()
    if not path.exists():
        return []
    resolved = str(Path(repo).expanduser().resolve())
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT payload_json FROM scans WHERE repo = ? ORDER BY id DESC LIMIT 2",
            (resolved,),
        ).fetchall()
    if len(rows) < 2:
        return []
    try:
        payload = json.loads(rows[1]["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return []
    return list(payload.get("verdicts") or [])


def setup_state_path() -> Path:
    return home_dir() / "setup_state.json"


def read_setup_state() -> dict[str, Any]:
    path = setup_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def write_setup_state(state: dict[str, Any]) -> Path:
    path = setup_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return path


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()
