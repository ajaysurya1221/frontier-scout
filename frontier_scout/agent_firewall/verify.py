"""PR scope verifier: did a PR's diff stay inside the policy's declared scope?

Runs in GitHub Actions (or locally) and answers two questions separately:

* **Scope** — is every path the PR changes (both ends of a rename, deletions, mode-only
  and binary changes) inside ``allowed_file_globs`` or a protected path? The diff is
  collected by the verifier itself with ``git diff --name-status -z -M``, and the policy
  and lock are read from the **base commit**, so a PR cannot widen its own scope by
  editing them (a PR that changes them is itself a protected change).
* **Approval provenance** — receipts are unsigned JSON written on the agent's machine, so
  nothing in a receipt (``decision``, ``realized``, an approval field) can authenticate a
  human approval. A changed protected path is therefore never a PASS: it is FAIL with no
  receipt at all and UNVERIFIED with one.

Every finding carries a stable reason code (:data:`REASON_CODES`). Anything that cannot
be established (no diff, malformed policy identity, malformed evidence) is never a PASS.
Output is **control evidence, not a guarantee**. The only subprocesses are read-only git
plumbing calls (``rev-parse``, ``diff``, ``ls-tree``, ``cat-file``) with a fixed argv.
"""

from __future__ import annotations

import glob as _glob
import json
import os
import re
import subprocess  # nosec B404 — only read-only git plumbing is run, with a fixed argv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from outputs._text import scrub_secrets

from .hook_runtime import _path_matches_glob, repo_relative
from .lock import LOCK_FILENAME, policy_hash
from .models import AgentPolicy
from .policy import MAX_POLICY_BYTES, POLICY_FILENAME

__all__ = [
    "verify_pr",
    "git_diff_changes",
    "git_diff_names",
    "load_receipts",
    "DiffChange",
    "Finding",
    "VerifyResult",
    "GitDiffError",
    "REASON_CODES",
]

Outcome = Literal["fail", "unverified", "warn"]

# Stable reason codes -> (outcome, meaning). "fail" and "unverified" findings are never a
# PASS in enforcing mode; "warn" findings never block.
REASON_CODES: dict[str, tuple[Outcome, str]] = {
    "POLICY_LOCK_MISSING": ("fail", "no policy.lock.json at the trusted policy source"),
    "POLICY_LOCK_MALFORMED": ("fail", "the lock is unreadable or lacks a sha256 policy_sha256"),
    "POLICY_MISSING": ("fail", "no frontier-scout.policy.json at the trusted policy source"),
    "POLICY_MALFORMED": ("fail", "the policy is unreadable, oversized, or fails the policy schema"),
    "POLICY_DRIFT": ("fail", "the policy no longer matches the hash in the lock"),
    "SCOPE_OUTSIDE_ALLOWED": ("fail", "a changed path is neither allowed nor protected"),
    "PROTECTED_NO_RECEIPT": ("fail", "a protected path changed and no receipt mentions it"),
    "RECEIPT_DENY_BYPASS": ("fail", "a path changed although a receipt records a deny for it"),
    "RECEIPT_MALFORMED": ("fail", "a receipt is not valid JSON or has invalid fields"),
    "RECEIPT_POLICY_HASH_MISSING": ("fail", "an action receipt is not bound to any policy hash"),
    "RECEIPT_STALE": ("fail", "an action receipt was written under a different policy"),
    "APPROVAL_UNAUTHENTICATED": (
        "unverified",
        "a protected path changed; receipts cannot authenticate who approved it",
    ),
    "DIFF_BASE_MISSING": ("unverified", "no base ref was given, so no PR diff was collected"),
    "DIFF_BASE_INVALID": ("unverified", "the base ref is empty, option-shaped, or has control characters"),
    "DIFF_FAILED": ("unverified", "git could not resolve the base or compute the PR diff"),
    "DIFF_UNPARSEABLE": ("unverified", "the git diff output had an unexpected shape"),
    "BASE_READ_FAILED": ("unverified", "git could not read the policy/lock from the base commit"),
    "POLICY_CHANGED_IN_PR": ("warn", "the PR changes the policy or lock; the base version governed"),
    "POLICY_UNPINNED": ("warn", "policy and lock were read from the working tree, not a base commit"),
    "RECEIPT_ABSENT": ("warn", "an in-scope path changed with no action receipt"),
    "RECEIPT_IN_PR": ("warn", "a receipt file is added or changed by the PR itself"),
    "RECEIPT_NOT_ACTION": ("warn", "a static `agent check` receipt was ignored (not action evidence)"),
}

# The verifier's own authority: always treated as protected, whatever the globs say.
GOVERNANCE_PATHS: tuple[str, ...] = (POLICY_FILENAME, LOCK_FILENAME)

_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_STATUS_RE = re.compile(r"^([ACDMRT])([0-9]{0,3})$")
_DECISIONS = frozenset({"allow", "ask", "deny"})
_VERDICTS = frozenset({"allow", "needs_approval", "block"})
_GIT_TIMEOUT = 30


class GitDiffError(Exception):
    """The PR diff (or the base it depends on) could not be collected. A failed diff is
    NOT an empty diff: the verifier reports it as UNVERIFIED, never as "0 changed files"."""

    def __init__(self, returncode: int, stderr: str, code: str = "DIFF_FAILED") -> None:
        self.returncode = returncode
        self.stderr = stderr or ""
        self.code = code
        super().__init__(f"git diff failed (exit {returncode})")


class Finding(BaseModel):
    code: str
    outcome: Outcome
    message: str
    path: str | None = None


class VerifyResult(BaseModel):
    ok: bool
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    checked_files: int = 0
    receipt_count: int = 0
    summary: str = ""
    unverified: bool = False
    # Advisory mode downgrades violations to warnings (ok=True), so exported
    # evidence must carry the mode or an advisory run reads as a clean pass.
    advisory: bool = False
    # The verdict is computed the same way in both modes; ``ok`` is what the mode does with it.
    verdict: Literal["pass", "fail", "unverified"] = "pass"
    # Scope and approval provenance are separate answers; see the module docstring.
    scope: Literal["verified", "violated", "not-evaluated"] = "not-evaluated"
    approval_provenance: Literal["not-required", "unauthenticated", "not-evaluated"] = "not-evaluated"
    policy_source: str = ""
    receipts_in_pr: int = 0
    reason_codes: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


@dataclass(frozen=True)
class DiffChange:
    """One ``git diff --name-status`` record. ``paths`` holds both ends of a rename/copy."""

    status: str
    paths: tuple[str, ...]


# --- git plumbing (read-only, fixed argv) --------------------------------------------


def _git(repo: str, *args: str) -> bytes:
    try:
        proc = subprocess.run(  # nosec B603 B607 — fixed argv, no shell, read-only git
            ["git", "-C", repo, *args], capture_output=True, check=False, timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitDiffError(-1, str(exc)) from exc
    if proc.returncode != 0:
        raise GitDiffError(proc.returncode, proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def _resolve_base(repo: str, base: str) -> str:
    """Resolve ``base`` to a commit sha. Option-shaped or control-character refs are
    rejected before git sees them (``--output=...`` must never reach ``git diff``)."""

    if not base or base.startswith("-") or any(ord(ch) < 0x20 or ch == "\x7f" for ch in base):
        raise GitDiffError(-1, "base ref is empty, starts with '-', or contains control characters",
                           code="DIFF_BASE_INVALID")
    sha = _git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").decode("ascii", "replace").strip()
    if not _SHA_RE.match(sha):
        raise GitDiffError(-1, f"could not resolve base to a commit: {sha[:80]}")
    return sha


def _parse_name_status_z(raw: bytes) -> list[DiffChange]:
    """Parse ``git diff --name-status -z`` output. Paths are NUL-delimited and unquoted,
    so spaces, tabs, quotes, newlines and non-UTF-8 bytes survive exactly."""

    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    changes: list[DiffChange] = []
    i = 0
    while i < len(tokens):
        status_text = tokens[i].decode("ascii", "replace")
        match = _STATUS_RE.match(status_text)
        if not match:
            raise GitDiffError(0, f"unexpected diff status {status_text[:20]!r}", code="DIFF_UNPARSEABLE")
        letter = match.group(1)
        width = 2 if letter in "RC" else 1
        raw_paths = tokens[i + 1 : i + 1 + width]
        if len(raw_paths) != width or any(not p for p in raw_paths):
            raise GitDiffError(0, "truncated diff record", code="DIFF_UNPARSEABLE")
        changes.append(DiffChange(letter, tuple(p.decode("utf-8", "surrogateescape") for p in raw_paths)))
        i += 1 + width
    return changes


def _diff_against(repo: str, sha: str) -> list[DiffChange]:
    raw = _git(
        repo, "diff", "--name-status", "-z", "-M", "--no-color", "--no-ext-diff", "--no-relative",
        f"{sha}...HEAD",
    )
    return _parse_name_status_z(raw)


def git_diff_changes(repo: str, base: str) -> list[DiffChange]:
    """Read-only ``git diff --name-status -z -M <base>...HEAD`` -> structured changes.

    Returns ``[]`` for a *successful* empty diff, but **raises** :class:`GitDiffError` on
    any failure (invalid or option-shaped base, unfetched history, unparseable output)."""

    return _diff_against(repo, _resolve_base(repo, base))


def _unique_paths(changes: list[DiffChange]) -> list[str]:
    return list(dict.fromkeys(p for change in changes for p in change.paths))


def git_diff_names(repo: str, base: str) -> list[str]:
    """Every path the PR touches (both ends of renames/copies), in diff order. Raises
    :class:`GitDiffError` on failure; a failed diff is never an empty one."""

    return _unique_paths(git_diff_changes(repo, base))


def _read_base_files(repo: str, sha: str) -> dict[str, bytes | str]:
    """Policy + lock blobs at the base commit. Value is the content, or a reason string
    when the entry is not a regular file or is oversized. Missing files are absent."""

    raw = _git(repo, "ls-tree", "-z", "-l", "--full-tree", sha, "--", *GOVERNANCE_PATHS)
    found: dict[str, bytes | str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, name_bytes = record.partition(b"\t")
        parts = meta.split()
        name = name_bytes.decode("utf-8", "replace")
        if name not in GOVERNANCE_PATHS:
            continue
        if len(parts) != 4 or parts[1] != b"blob" or parts[0] not in (b"100644", b"100755"):
            found[name] = "not a regular file"
            continue
        if not parts[3].isdigit() or int(parts[3]) > MAX_POLICY_BYTES:
            found[name] = f"larger than {MAX_POLICY_BYTES} bytes"
            continue
        found[name] = _git(repo, "cat-file", "blob", parts[2].decode("ascii"))
    return found


def _read_worktree_files(repo: str) -> dict[str, bytes | str]:
    found: dict[str, bytes | str] = {}
    for name in GOVERNANCE_PATHS:
        path = Path(repo) / name
        try:
            if not path.is_file():
                continue
            if path.stat().st_size > MAX_POLICY_BYTES:
                found[name] = f"larger than {MAX_POLICY_BYTES} bytes"
                continue
            found[name] = path.read_bytes()
        except OSError as exc:
            found[name] = f"unreadable ({type(exc).__name__})"
    return found


# --- findings -------------------------------------------------------------------------


def _printable(text: str) -> str:
    """Render untrusted text (file names, git stderr, refs) on one line: control
    characters are escaped, an undecodable filename byte (kept by ``surrogateescape``)
    becomes the marker ``\\xNN``, and secret-shaped tokens are scrubbed. The result is
    always encodable, so JSON and stdout emission cannot fail on it."""

    parts: list[str] = []
    for ch in text:
        if "\udc80" <= ch <= "\udcff":
            parts.append(f"\\x{ord(ch) - 0xDC00:02x}")
        elif ch.isprintable():
            parts.append(ch)
        else:
            parts.append(ascii(ch)[1:-1])
    return scrub_secrets("".join(parts))


def _annotation_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _annotation_property(text: str) -> str:
    return _annotation_data(text).replace(":", "%3A").replace(",", "%2C")


@dataclass
class _Collector:
    findings: list[Finding] = field(default_factory=list)

    def add(self, code: str, message: str, path: str | None = None) -> None:
        # ``path`` is the raw name used for matching; the exported copy (JSON field and
        # annotation ``file=``) goes through the same scrubber as the message.
        outcome = REASON_CODES[code][0]
        shown = None if path is None else _printable(path)
        self.findings.append(Finding(code=code, outcome=outcome, message=message, path=shown))

    def has(self, code: str) -> bool:
        return any(f.code == code for f in self.findings)


@dataclass
class _ActionReceipt:
    label: str
    denied: bool
    files: frozenset[str]
    in_pr: bool


# --- policy identity ------------------------------------------------------------------


def _evaluate_identity(
    files: dict[str, bytes | str], source: str, out: _Collector
) -> tuple[AgentPolicy | None, str | None]:
    """Return (governing policy, lock hash). The policy governs only when the lock is
    well formed, the policy validates against the schema, and its hash matches the lock."""

    expected: str | None = None
    lock_blob = files.get(LOCK_FILENAME)
    if lock_blob is None:
        out.add("POLICY_LOCK_MISSING",
                f"No {LOCK_FILENAME} in the {source}: the repo was not compiled there "
                "(run `agent compile` and merge the result before relying on verify-pr).")
    else:
        lock: Any = None
        if isinstance(lock_blob, bytes):
            try:
                lock = json.loads(lock_blob.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                lock = None
        value = lock.get("policy_sha256") if isinstance(lock, dict) else None
        if isinstance(value, str) and _HASH_RE.match(value):
            expected = value
        else:
            out.add("POLICY_LOCK_MALFORMED",
                    f"{LOCK_FILENAME} in the {source} is unreadable or has no sha256 policy_sha256; "
                    "the policy identity cannot be established.")

    policy_blob = files.get(POLICY_FILENAME)
    if policy_blob is None:
        out.add("POLICY_MISSING", f"{POLICY_FILENAME} is missing from the {source}.")
        return None, expected
    data: Any = None
    if isinstance(policy_blob, bytes):
        try:
            data = json.loads(policy_blob.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            data = None
    policy: AgentPolicy | None = None
    if isinstance(data, dict):
        try:
            policy = AgentPolicy.model_validate(data)
        except ValidationError:
            policy = None
    if policy is None or not isinstance(data, dict):
        out.add("POLICY_MALFORMED",
                f"{POLICY_FILENAME} in the {source} is not valid JSON or does not match the policy "
                "schema; scope cannot be evaluated.")
        return None, expected
    if expected is not None and policy_hash(data) != expected:
        out.add("POLICY_DRIFT",
                f"Policy drifted: {POLICY_FILENAME} in the {source} no longer matches the lock. "
                "Re-run `agent compile`.")
        return None, expected
    return (policy if expected is not None else None), expected


# --- receipts -------------------------------------------------------------------------


def _receipt_files(repo: str, pattern: str | None) -> list[str]:
    paths: list[str] = []
    if pattern:
        paths = _glob.glob(pattern) or _glob.glob(os.path.join(repo, pattern))
    else:
        for sub in ("frontier-scout-receipts", os.path.join(".frontier-scout", "receipts")):
            paths += _glob.glob(os.path.join(repo, sub, "*.json"))
    return sorted(set(paths))


def load_receipts(repo: str, pattern: str | None = None) -> list[dict[str, Any]]:
    """Load receipt JSON objects. ``pattern`` (a glob) wins; else the default evidence dirs
    (``frontier-scout-receipts/`` and the local ``.frontier-scout/receipts/``).

    Convenience reader only: it skips unreadable files. ``verify_pr`` does not use it;
    it loads the same files strictly and reports a malformed one as ``RECEIPT_MALFORMED``."""

    receipts: list[dict[str, Any]] = []
    for path in _receipt_files(repo, pattern):
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            receipts.append(data)
    return receipts


def _check_receipt(
    data: Any, label: str, in_pr: bool, repo: str, expected: str | None, out: _Collector
) -> _ActionReceipt | None:
    """Validate one receipt. Returns it when it is well-formed action evidence."""

    def malformed(why: str) -> None:
        out.add("RECEIPT_MALFORMED",
                f"Receipt {label} is malformed ({why}); malformed evidence is never accepted.")

    if not isinstance(data, dict):
        malformed("not a JSON object")
        return None
    kind = data.get("kind")
    receipt_id = data.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        malformed("no receipt_id")
        return None
    name = _printable(receipt_id)[:120]
    if kind == "static-policy-assessment":
        out.add("RECEIPT_NOT_ACTION",
                f"Receipt {name} is a static `agent check` assessment, not action evidence; ignored.")
        return None
    if kind != "agent-action":
        malformed(f"unknown kind {_printable(str(kind))[:40]!r}")
        return None
    decision = data.get("decision")
    verdict = data.get("verdict")
    files = data.get("files_considered", [])
    ph = data.get("policy_hash")
    # Type-check before membership: an array or object is unhashable in a frozenset test.
    if not isinstance(decision, str) or decision not in _DECISIONS:
        malformed("decision is not allow/ask/deny")
        return None
    if verdict is not None and (not isinstance(verdict, str) or verdict not in _VERDICTS):
        malformed("verdict is not allow/needs_approval/block")
        return None
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        malformed("files_considered is not a list of strings")
        return None
    if ph is not None and not isinstance(ph, str):
        malformed("policy_hash is not a string")
        return None
    if not ph:
        out.add("RECEIPT_POLICY_HASH_MISSING",
                f"Receipt {name} has no policy_hash, so it cannot be bound to the locked policy.")
    elif expected is not None and ph != expected:
        out.add("RECEIPT_STALE",
                f"Receipt {name} was written under a different policy (stale policy hash); "
                "evidence does not match the locked policy.")
    return _ActionReceipt(
        label=name, denied=decision == "deny" or verdict == "block", in_pr=in_pr,
        files=frozenset(repo_relative(f, repo) for f in files),
    )


# --- verify ---------------------------------------------------------------------------


def verify_pr(
    repo: str,
    *,
    base: str | None = None,
    changed_files: list[str] | None = None,
    receipts: list[dict[str, Any]] | None = None,
    receipts_glob: str | None = None,
    advisory: bool = False,
) -> VerifyResult:
    """Check a PR's diff against the base commit's policy scope; report approval
    provenance separately. Never returns PASS for anything it could not establish.

    ``base`` is the trusted base ref: the diff is ``<base>...HEAD`` and the policy + lock
    are read from ``<base>``. ``changed_files`` (programmatic use) skips the diff; without
    ``base`` the policy is then read from the working tree and flagged ``POLICY_UNPINNED``.
    """

    out = _Collector()
    shown_base = _printable(base or "")[:200]

    # 1. Resolve the trusted base and collect the diff.
    sha: str | None = None
    changes: list[DiffChange] | None = None
    diff_error: GitDiffError | None = None
    if base is not None:
        try:
            sha = _resolve_base(repo, base)
            if changed_files is None:
                changes = _diff_against(repo, sha)
        except GitDiffError as exc:
            diff_error = exc
    if changed_files is not None:
        changes = [DiffChange("M", (p,)) for p in changed_files]
    if diff_error is not None:
        stderr = _printable(diff_error.stderr)[:300] or "no further detail from git"
        if diff_error.code == "DIFF_BASE_INVALID":
            out.add("DIFF_BASE_INVALID", f"Base ref '{shown_base}' was rejected ({stderr}); nothing was verified.")
        else:
            out.add(diff_error.code if diff_error.code in REASON_CODES else "DIFF_FAILED",
                    f"Could not compute the PR diff against base '{shown_base}' in repo '{_printable(repo)}' "
                    f"(git exited {diff_error.returncode}): {stderr}. Ensure the base ref/history is "
                    "fetched (the generated workflow uses fetch-depth: 0).")
    elif changes is None:
        out.add("DIFF_BASE_MISSING",
                "No --base was given, so no PR diff was collected and nothing was verified.")

    # 2. Policy identity from the trusted base (or the working tree, flagged).
    policy: AgentPolicy | None = None
    expected: str | None = None
    policy_source = "not read"
    if sha is not None:
        policy_source = f"base {sha[:12]}"
        try:
            files = _read_base_files(repo, sha)
        except GitDiffError as exc:
            out.add("BASE_READ_FAILED",
                    f"Could not read the policy/lock from base {sha[:12]} "
                    f"(git exited {exc.returncode}): {_printable(exc.stderr)[:200]}.")
        else:
            policy, expected = _evaluate_identity(files, f"base commit {sha[:12]}", out)
    elif base is None:
        policy_source = "working tree"
        if changes is not None:
            out.add("POLICY_UNPINNED",
                    "Policy and lock were read from the working tree, not from a base commit; pass "
                    "--base to evaluate scope against the trusted base policy.")
        policy, expected = _evaluate_identity(_read_worktree_files(repo), "working tree", out)

    changed = _unique_paths(changes or [])
    changed_set = set(changed)
    status_of = {p: c.status for c in (changes or []) for p in c.paths}

    # 3. Receipts: strictly loaded, never authorising.
    action_receipts: list[_ActionReceipt] = []
    receipt_count = 0
    receipts_in_pr = 0
    if receipts is not None:
        for index, item in enumerate(receipts):
            receipt_count += 1
            label = str(item.get("receipt_id", f"#{index}")) if isinstance(item, dict) else f"#{index}"
            checked = _check_receipt(item, _printable(label)[:120], False, repo, expected, out)
            if checked is not None:
                action_receipts.append(checked)
    else:
        for file_path in _receipt_files(repo, receipts_glob):
            receipt_count += 1
            rel = repo_relative(os.path.abspath(file_path), repo)
            in_pr = rel in changed_set
            if in_pr:
                receipts_in_pr += 1
                out.add("RECEIPT_IN_PR",
                        f"{_printable(rel)}: receipt file added or changed by this PR; it is PR-authored "
                        "and is treated as an unauthenticated observation.", rel)
            try:
                if Path(file_path).stat().st_size > MAX_POLICY_BYTES:
                    raise ValueError("oversized receipt")
                data: Any = json.loads(Path(file_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                out.add("RECEIPT_MALFORMED",
                        f"Receipt {_printable(rel)} is malformed (unreadable, oversized or not JSON); "
                        "malformed evidence is never accepted.", rel)
                continue
            checked = _check_receipt(data, _printable(rel), in_pr, repo, expected, out)
            if checked is not None:
                action_receipts.append(checked)

    # 4. Scope (needs a diff and a governing policy) and approval provenance.
    scope: Literal["verified", "violated", "not-evaluated"] = "not-evaluated"
    provenance: Literal["not-required", "unauthenticated", "not-evaluated"] = "not-evaluated"
    protected_count = 0
    if changes is not None and policy is not None and diff_error is None:
        for path in changed:
            shown = _printable(path)
            status = status_of.get(path, "M")
            covering = [r for r in action_receipts if path in r.files]
            for r in covering:
                if r.denied:
                    out.add("RECEIPT_DENY_BYPASS",
                            f"{shown}: changed despite a deny decision in receipt {r.label} (policy bypass).", path)
            governance = path in GOVERNANCE_PATHS
            if governance:
                out.add("POLICY_CHANGED_IN_PR",
                        f"{shown}: this PR changes the verifier's policy/lock; scope was evaluated against "
                        "the base commit's version, and the change itself needs approval.", path)
            if governance or any(_path_matches_glob(path, g) for g in policy.protected_file_globs):
                protected_count += 1
                if not covering:
                    out.add("PROTECTED_NO_RECEIPT",
                            f"{shown}: protected path changed ({status}) without an action receipt (fail-closed).",
                            path)
                else:
                    from_pr = sum(1 for r in covering if r.in_pr)
                    note = f", {from_pr} of them added by this PR" if from_pr else ""
                    out.add("APPROVAL_UNAUTHENTICATED",
                            f"{shown}: protected path changed ({status}); approval provenance not authenticated: "
                            f"{len(covering)} unsigned receipt(s) mention it{note}, and receipt decision/approval "
                            "fields are self-reported, so they cannot authorise a protected change. "
                            "A human must approve it out of band.", path)
            elif not any(_path_matches_glob(path, g) for g in policy.allowed_file_globs):
                out.add("SCOPE_OUTSIDE_ALLOWED",
                        f"{shown}: changed ({status}) outside allowed_file_globs and not a protected path "
                        "(out of scope).", path)
            elif not covering:
                out.add("RECEIPT_ABSENT",
                        f"{shown}: changed with no action receipt (hooks may not be installed).", path)
        scope = "violated" if out.has("SCOPE_OUTSIDE_ALLOWED") else "verified"
        provenance = "unauthenticated" if protected_count else "not-required"

    return _result(
        out, advisory=advisory, scope=scope, provenance=provenance, protected_count=protected_count,
        checked=len(changed), receipt_count=receipt_count, receipts_in_pr=receipts_in_pr,
        policy_source=policy_source, no_diff=changes is None or diff_error is not None, shown_base=shown_base,
    )


def _result(
    out: _Collector,
    *,
    advisory: bool,
    scope: Literal["verified", "violated", "not-evaluated"],
    provenance: Literal["not-required", "unauthenticated", "not-evaluated"],
    protected_count: int,
    checked: int,
    receipt_count: int,
    receipts_in_pr: int,
    policy_source: str,
    no_diff: bool,
    shown_base: str,
) -> VerifyResult:
    findings = out.findings
    blocking = [f for f in findings if f.outcome != "warn"]
    verdict: Literal["pass", "fail", "unverified"]
    if any(f.outcome == "fail" for f in findings):
        verdict = "fail"
    elif blocking:
        verdict = "unverified"
    else:
        verdict = "pass"

    def text(f: Finding) -> str:
        return f"[{f.code}] {f.message}"

    violations = [] if advisory else [text(f) for f in blocking]
    warnings = [text(f) for f in findings if f.outcome == "warn"]
    if advisory:
        warnings += [text(f) for f in blocking]
    annotations: list[str] = []
    for f in findings:
        level = "error" if (f.outcome != "warn" and not advisory) else "warning"
        where = f" file={_annotation_property(f.path)}" if f.path else ""
        annotations.append(f"::{level}{where}::{_annotation_data(text(f))}")

    if scope == "verified":
        scope_text = "verified (every changed path is allowed or protected by the base policy)"
    elif scope == "violated":
        n = sum(1 for f in findings if f.code == "SCOPE_OUTSIDE_ALLOWED")
        scope_text = f"violated ({n} path(s) outside allowed_file_globs)"
    elif no_diff:
        scope_text = f"not evaluated (no PR diff{f' against base {shown_base!r}' if shown_base else ''})"
    else:
        scope_text = "not evaluated (no valid policy identity)"
    if provenance == "not-required":
        provenance_text = "not required (no protected path changed)"
    elif provenance == "unauthenticated":
        provenance_text = f"not authenticated for {protected_count} protected path(s) (receipts are unsigned)"
    else:
        provenance_text = "not evaluated"
    mode = " (advisory: reported, not enforced)" if advisory else ""
    summary = (
        f"{verdict.upper()}{mode}: scope {scope_text}; approval provenance {provenance_text}; "
        f"{checked} changed file(s), {receipt_count} receipt(s), {len(violations)} violation(s), "
        f"{len(warnings)} warning(s)."
    )
    return VerifyResult(
        ok=advisory or verdict == "pass",
        violations=violations,
        warnings=warnings,
        annotations=annotations,
        checked_files=checked,
        receipt_count=receipt_count,
        summary=summary,
        unverified=any(f.outcome == "unverified" for f in findings),
        advisory=advisory,
        verdict=verdict,
        scope=scope,
        approval_provenance=provenance,
        policy_source=policy_source,
        receipts_in_pr=receipts_in_pr,
        reason_codes=sorted({f.code for f in findings}),
        findings=findings,
    )
