"""Static, advisory audit receipts for ``frontier-scout agent check``.

A receipt is a JSON record of a *static policy assessment* — it never implies
the task ran. Receipts live under ``<repo>/.frontier-scout/receipts/`` (the
``.frontier-scout`` dir is already scan-excluded). Task text is redacted at the
write boundary via :func:`sanitize_sensitive_text` before it is ever persisted.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frontier_scout import __version__
from frontier_scout.agent_firewall.models import Receipt, TaskDecision
from frontier_scout.store import _now
from outputs._text import sanitize_sensitive_text

__all__ = ["receipts_dir", "write_receipt", "list_receipts", "show_receipt"]

# Belt-and-suspenders mask applied at the receipt write boundary, *after*
# sanitize_sensitive_text. The canonical redactor only collapses secret-shaped
# tokens above a length floor (sk-ant-{20,}); this masks the same key shapes
# down to their prefix so a short-but-real token can never land in a receipt.
# Not a parallel risk taxonomy — a redaction backstop for persisted task text.
_KEY_SHAPE = re.compile(r"\b(sk-ant-|sk-|ghp_|github_pat_|xox[baprs]-|npm_)[A-Za-z0-9\-_]+")

_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def receipts_dir(repo: str) -> Path:
    """Directory holding this repo's audit receipts (created on demand)."""
    return Path(repo) / ".frontier-scout" / "receipts"


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text).lower()[:40].strip("-") or "task"


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _redact(text: str) -> str:
    """Redact secret-shaped tokens from persisted task text (write boundary)."""
    out = sanitize_sensitive_text(text)
    return _KEY_SHAPE.sub(lambda m: m.group(1) + "REDACTED", out)


def _git_meta(repo: str) -> tuple[str | None, str | None]:
    """Read-only git branch + short commit; ``(None, None)`` on any failure.

    This is a guarded, read-only metadata query (``git rev-parse``), not task
    execution. It never mutates the repo and tolerates a non-git directory.
    """
    branch: str | None = None
    commit: str | None = None
    try:
        branch = _git_query(repo, "--abbrev-ref", "HEAD")
        commit = _git_query(repo, "--short", "HEAD")
    except Exception:
        return (None, None)
    return (branch, commit)


def _git_query(repo: str, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "rev-parse", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or "").strip()
    return value or None


def write_receipt(
    decision: TaskDecision,
    *,
    repo: str,
    task: str,
    policy_path: str | None,
) -> str:
    """Persist a static-assessment receipt for ``decision``; return its id.

    The task text is redacted before storage and clipped to 500 chars. No MCP
    server, agent task, or network call runs here — this only records evidence.
    """
    branch, commit = _git_meta(repo)
    receipt_id = f"{_now_stamp()}-{_slug(task)}"
    receipt = Receipt(
        receipt_id=receipt_id,
        timestamp=_now(),
        repo=repo,
        git_branch=branch,
        git_commit=commit,
        task_summary=_redact(task)[:500],
        policy_path=policy_path,
        verdict=decision.verdict,
        reasons=[r.model_dump() for r in decision.reasons],
        files_considered=list(decision.files_considered),
        required_checks=list(decision.required_checks),
        warnings=list(decision.warnings),
        frontier_scout_version=__version__,
    )
    directory = receipts_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{receipt_id}.json"
    path.write_text(json.dumps(receipt.model_dump(), indent=2, default=str) + "\n")
    return receipt_id


def list_receipts(repo: str) -> list[dict[str, Any]]:
    """All receipts, newest first; tolerant of missing dir / corrupt files."""
    directory = receipts_dir(repo)
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            data: dict[str, Any] = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        items.append(data)
    return items


def show_receipt(repo: str, receipt_id: str) -> dict[str, Any] | None:
    """Load one receipt by id (with or without the ``.json`` suffix).

    Returns ``None`` if it is missing or cannot be parsed.
    """
    directory = receipts_dir(repo)
    stem = receipt_id[:-5] if receipt_id.endswith(".json") else receipt_id
    path = directory / f"{stem}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data
