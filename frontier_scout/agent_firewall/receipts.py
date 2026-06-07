"""Static, advisory audit receipts for ``frontier-scout agent check``.

A receipt is a JSON record of a *static policy assessment* — it never implies
the task ran. Receipts live under ``<repo>/.frontier-scout/receipts/`` (the
``.frontier-scout`` dir is already scan-excluded). Task text is redacted at the
write boundary via :func:`sanitize_sensitive_text` before it is ever persisted.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 — only read-only `git rev-parse` is run, with a fixed argv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frontier_scout import __version__
from frontier_scout.agent_firewall.models import Receipt, TaskDecision
from outputs._text import scrub_secrets

__all__ = ["receipts_dir", "write_receipt", "list_receipts", "show_receipt"]

_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _now() -> str:
    """ISO-8601 UTC timestamp (inlined from the former store module)."""
    return datetime.now(UTC).isoformat()


def receipts_dir(repo: str) -> Path:
    """Directory holding this repo's audit receipts (created on demand)."""
    return Path(repo) / ".frontier-scout" / "receipts"


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text).lower()[:40].strip("-") or "task"


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _redact(text: str) -> str:
    """Redact secret-shaped tokens (incl. short ones) at the write boundary."""
    return scrub_secrets(text)


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
        proc = subprocess.run(  # nosec B603 B607 — fixed argv, no shell, read-only git
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
    # Redact EVERY persisted string field, not just the task — a secret-shaped
    # token can ride in a changed-file path, a reason message, a warning, or a
    # branch name. The receipt is a durable, shareable artifact.
    reasons = []
    for r in decision.reasons:
        item = r.model_dump()
        item["message"] = _redact(str(item.get("message", "")))
        item["tool_name"] = _redact(str(item.get("tool_name", "")))
        reasons.append(item)
    receipt = Receipt(
        receipt_id=receipt_id,
        timestamp=_now(),
        repo=repo,
        git_branch=_redact(branch) if branch else None,
        git_commit=commit,
        task_summary=_redact(task)[:500],
        policy_path=policy_path,
        verdict=decision.verdict,
        reasons=reasons,
        files_considered=[_redact(f) for f in decision.files_considered],
        required_checks=list(decision.required_checks),
        warnings=[_redact(w) for w in decision.warnings],
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

    ``receipt_id`` is attacker-controllable (a CLI positional), so it is
    constrained to a single, contained filename — any path separator, parent
    reference, or absolute path is rejected (no traversal, no arbitrary read).
    Returns ``None`` if it is missing, escapes the receipts dir, or can't parse.
    """
    directory = receipts_dir(repo)
    stem = receipt_id[:-5] if receipt_id.endswith(".json") else receipt_id
    # Reject anything that isn't a plain filename component.
    if not stem or stem in (".", "..") or "/" in stem or "\\" in stem:
        return None
    if ".." in Path(stem).parts or Path(stem).is_absolute():
        return None
    path = directory / f"{stem}.json"
    # Defense in depth: confirm the resolved path stays inside the receipts dir.
    try:
        base = directory.resolve()
        target = path.resolve()
        if base != target and base not in target.parents:
            return None
    except OSError:
        return None
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data
