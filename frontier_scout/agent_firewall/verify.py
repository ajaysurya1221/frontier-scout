"""PR receipt verifier: did the PR stay within the approved policy scope?

Runs in GitHub Actions (or locally). It reads the policy lock, the action receipts
the native hook emitted, and the actual PR diff, then checks — **fail-closed** —
that every protected change is backed by evidence and that no denied action slipped
through. It emits config-and-evidence findings; it is **control evidence, not a
guarantee** that no unsafe action occurred. The only subprocess is a read-only
``git diff`` (never task execution).
"""

from __future__ import annotations

import glob as _glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .hook_runtime import _path_matches_glob
from .lock import default_lock_path, policy_hash, read_lock
from .policy import default_policy_path, load_policy

__all__ = ["verify_pr", "git_diff_names", "load_receipts", "VerifyResult"]


class VerifyResult(BaseModel):
    ok: bool
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    checked_files: int = 0
    receipt_count: int = 0
    summary: str = ""


def git_diff_names(repo: str, base: str) -> list[str]:
    """Read-only ``git diff --name-only <base>...HEAD``; ``[]`` on any failure."""

    try:
        proc = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def load_receipts(repo: str, pattern: str | None = None) -> list[dict[str, Any]]:
    """Load receipt JSON. ``pattern`` (a glob) wins; else the default evidence dirs
    (``frontier-scout-receipts/`` for committed/CI evidence and the local
    ``.frontier-scout/receipts/``)."""

    paths: list[str] = []
    if pattern:
        paths = _glob.glob(pattern) or _glob.glob(os.path.join(repo, pattern))
    else:
        for sub in ("frontier-scout-receipts", os.path.join(".frontier-scout", "receipts")):
            paths += _glob.glob(os.path.join(repo, sub, "*.json"))
    receipts: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        try:
            receipts.append(json.loads(Path(path).read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return receipts


def _raw_policy_hash(policy_path: str) -> str | None:
    try:
        return policy_hash(json.loads(Path(policy_path).read_text()))
    except (OSError, json.JSONDecodeError):
        return None


def verify_pr(
    repo: str,
    *,
    base: str | None = None,
    changed_files: list[str] | None = None,
    receipts: list[dict[str, Any]] | None = None,
    receipts_glob: str | None = None,
    advisory: bool = False,
) -> VerifyResult:
    """Verify a PR's receipts + diff against the locked policy. Fail-closed."""

    violations: list[str] = []
    warnings: list[str] = []
    annotations: list[str] = []

    policy, _ = load_policy(default_policy_path(repo))
    lock = read_lock(default_lock_path(repo))
    expected_hash = lock.get("policy_sha256") if lock else None

    if lock is None:
        violations.append("No policy.lock.json — repo not compiled (run `agent compile`).")
    else:
        current = _raw_policy_hash(default_policy_path(repo))
        if current is None:
            violations.append("policy.lock.json present but the policy file is missing/unreadable.")
        elif expected_hash and current != expected_hash:
            violations.append(
                "Policy drifted since compile: frontier-scout.policy.json no longer matches "
                "the lock. Re-run `agent compile`."
            )

    if changed_files is None:
        changed_files = git_diff_names(repo, base) if base else []
    if receipts is None:
        receipts = load_receipts(repo, receipts_glob)

    # Stale receipts: written under a different policy than the lock.
    if expected_hash:
        for r in receipts:
            if r.get("policy_hash") and r.get("policy_hash") != expected_hash:
                violations.append(
                    f"Receipt {r.get('receipt_id', '?')} was written under a different policy "
                    "(stale hash); evidence does not match the locked policy."
                )

    for path in changed_files:
        protected = any(_path_matches_glob(path, g) for g in policy.protected_file_globs)
        covering = [r for r in receipts if path in (r.get("files_considered") or [])]
        denied = [r for r in covering if r.get("decision") == "deny"]
        if denied:
            msg = f"{path}: changed despite a deny decision (policy bypass)."
            violations.append(msg)
            annotations.append(f"::error file={path}::{msg}")
        elif protected and not covering:
            msg = f"{path}: protected path changed without an action receipt (fail-closed)."
            violations.append(msg)
            annotations.append(f"::error file={path}::{msg}")
        elif not covering:
            msg = f"{path}: changed with no action receipt (hooks may not be installed)."
            warnings.append(msg)
            annotations.append(f"::warning file={path}::{msg}")

    if advisory:
        warnings = [*warnings, *violations]
        violations = []
        annotations = [a.replace("::error", "::warning") for a in annotations]

    ok = not violations
    summary = (
        f"{'PASS' if ok else 'FAIL'}: {len(changed_files)} changed file(s), "
        f"{len(receipts)} receipt(s), {len(violations)} violation(s), {len(warnings)} warning(s)."
    )
    return VerifyResult(
        ok=ok, violations=violations, warnings=warnings, annotations=annotations,
        checked_files=len(changed_files), receipt_count=len(receipts), summary=summary,
    )
