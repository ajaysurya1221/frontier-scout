"""Implement & Test — apply a tool/upgrade to the repo in isolation, run tests.

This is the v1.4.0 "close the loop" feature. The rest of Frontier Scout
*recommends*; this module *does* — but never on the user's working tree.

Flow (``run_implement``):

  1. Stage an isolated copy of the repo — a detached ``git worktree`` when the
     repo is a git checkout, otherwise a shallow file copy into a temp dir.
  2. Ask the LLM for the **minimal** code change that adopts the tool, as a
     structured set of file writes + a test command + a plain-language
     "what you get" summary.
  3. Apply the writes inside the isolated copy (path-jailed — no escape, no
     absolute paths, no ``..``).
  4. Run the repo's own test command in the copy under a hermetic env (real
     HOME hidden, secrets scrubbed). Capture pass/fail + output.
  5. Return an :class:`ImplementResult` carrying status, the unified diff,
     the test transcript, and the "what you get" note.

The caller then decides:

  * **Keep**  → :func:`keep_changes` copies the changed files into the real
    working tree (still no commit — the user reviews and commits).
  * **Discard** → :func:`discard` removes the worktree / temp dir.

Trust boundary mirrors the lab + dep-trial: the test subprocess never sees the
parent's API keys, and the working tree is only mutated on an explicit Keep.

``dry_run=True`` (or no provider available) produces a deterministic
"prepared" result with a synthetic, inert change so the plumbing — and the
test suite — works offline with zero spend.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Tool schema for the LLM code-change pass ────────────────────────────────

IMPLEMENT_TOOL: dict[str, Any] = {
    "name": "emit_code_change",
    "description": (
        "Emit the MINIMAL code change that adopts the requested tool/upgrade "
        "into this repository. Prefer the smallest diff that demonstrates the "
        "tool working and is covered by a test. Never touch unrelated files. "
        "Never write secrets, credentials, or absolute paths. Paths are "
        "relative to the repo root and must stay inside it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One sentence describing the change.",
                "minLength": 8,
                "maxLength": 300,
            },
            "what_you_get": {
                "type": "string",
                "description": (
                    "Plain-language payoff for the user — what this unlocks in "
                    "their repo once kept. No marketing voice."
                ),
                "minLength": 8,
                "maxLength": 400,
            },
            "files": {
                "type": "array",
                "description": "Files to create or modify (full new contents).",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Repo-relative path. No leading slash, no '..'.",
                            "maxLength": 300,
                        },
                        "action": {
                            "type": "string",
                            "enum": ["create", "modify"],
                        },
                        "contents": {
                            "type": "string",
                            "description": "Full new file contents after the change.",
                        },
                    },
                    "required": ["path", "action", "contents"],
                },
                "minItems": 1,
            },
            "test_command": {
                "type": "string",
                "description": (
                    "Command that verifies the change (e.g. 'pytest -q "
                    "tests/test_new.py'). Leave empty to use the repo default."
                ),
                "maxLength": 200,
            },
        },
        "required": ["summary", "what_you_get", "files"],
    },
}

_TIMEOUT = int(os.environ.get("FRONTIER_SCOUT_IMPLEMENT_TIMEOUT", "600"))
_MAX_TOKENS = int(os.environ.get("FRONTIER_SCOUT_IMPLEMENT_MAX_TOKENS", "8000"))


@dataclass
class ImplementResult:
    """Outcome of one Implement & Test run."""

    tool_name: str
    status: str  # prepared | passed | failed | error
    summary: str
    what_you_get: str
    files_changed: list[str] = field(default_factory=list)
    diff: str = ""
    test_command: str = ""
    test_output: str = ""
    exit_code: int = 0
    duration_s: int = 0
    cost_usd: float = 0.0
    workspace: str = ""  # isolated copy path; consumed by keep/discard
    is_worktree: bool = False
    repo: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "summary": self.summary,
            "what_you_get": self.what_you_get,
            "files_changed": list(self.files_changed),
            "diff": self.diff,
            "test_command": self.test_command,
            "test_output": self.test_output,
            "exit_code": self.exit_code,
            "duration_s": self.duration_s,
            "cost_usd": self.cost_usd,
            "workspace": self.workspace,
            "is_worktree": self.is_worktree,
            "repo": self.repo,
            "error": self.error,
        }


# ── Path safety ─────────────────────────────────────────────────────────────


def _safe_relpath(path: str) -> str | None:
    """Return a normalised repo-relative path, or None if it escapes the root."""
    if not path:
        return None
    p = path.strip().replace("\\", "/")
    if p.startswith("/") or p.startswith("~"):
        return None
    # Reject Windows drive letters too (e.g. C:\...).
    if len(p) >= 2 and p[1] == ":":
        return None
    norm = os.path.normpath(p)
    if norm == "." or norm.startswith("..") or norm.startswith("/"):
        return None
    parts = Path(norm).parts
    if ".." in parts:
        return None
    return norm


# ── Isolated workspace ──────────────────────────────────────────────────────


def _is_git_repo(repo: Path) -> bool:
    try:
        out = subprocess.run(  # noqa: S603 — fixed args, no shell
            ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _make_workspace(repo: Path) -> tuple[Path, bool]:
    """Create an isolated copy of the repo. Returns (path, is_worktree)."""
    temp_dir = Path(tempfile.mkdtemp(prefix="frontier-scout-implement-"))
    workspace = temp_dir / "repo"
    if _is_git_repo(repo):
        try:
            subprocess.run(  # noqa: S603 — fixed args, no shell
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(workspace), "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            return workspace, True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Fall through to a plain copy.
            pass
    shutil.copytree(
        repo,
        workspace,
        ignore=shutil.ignore_patterns(
            ".git", "node_modules", ".venv", "venv", "__pycache__",
            ".scratch", ".mypy_cache", ".pytest_cache", "*.pyc",
        ),
        symlinks=False,
    )
    return workspace, False


def _hermetic_env(workspace: Path) -> dict[str, str]:
    """Env for the test subprocess — secrets scrubbed, real HOME hidden."""
    home = workspace.parent / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TMPDIR": str(workspace.parent),
        "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "NO_UPDATE_NOTIFIER": "1",
    }
    # Preserve the active interpreter context so the repo's deps resolve, but
    # NOT the API keys or cloud creds.
    for key in ("VIRTUAL_ENV", "PYTHONPATH", "CONDA_PREFIX"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def default_test_command(repo: Path) -> str:
    """Best-effort detection of the repo's test runner."""
    makefile = repo / "Makefile"
    if makefile.exists():
        try:
            if "test:" in makefile.read_text(errors="ignore"):
                return "make test"
        except OSError:
            pass
    if (repo / "package.json").exists():
        return "npm test"
    return "pytest -q"


# ── Diff + apply ─────────────────────────────────────────────────────────────


def _git_diff(workspace: Path, is_worktree: bool) -> str:
    if not is_worktree:
        return ""
    try:
        # Mark new files as intent-to-add so they appear in `git diff` without
        # fully staging blobs into the index.
        subprocess.run(  # noqa: S603 — fixed args, no shell
            ["git", "-C", str(workspace), "add", "-N", "-A"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        out = subprocess.run(  # noqa: S603 — fixed args, no shell
            ["git", "-C", str(workspace), "diff", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        full = subprocess.run(  # noqa: S603 — fixed args, no shell
            ["git", "-C", str(workspace), "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return (out.stdout + "\n" + full.stdout).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _apply_files(workspace: Path, files: list[dict[str, Any]]) -> list[str]:
    """Write the proposed files into the workspace. Returns applied rel paths."""
    applied: list[str] = []
    root = workspace.resolve()
    for spec in files:
        rel = _safe_relpath(str(spec.get("path") or ""))
        if rel is None:
            continue
        target = (workspace / rel).resolve()
        # Final jail check: the resolved path must stay under the workspace.
        if root not in target.parents and target != root:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(spec.get("contents") or ""))
        applied.append(rel)
    return applied


# ── Synthetic (offline) change ───────────────────────────────────────────────


def _synthetic_change(tool_name: str) -> dict[str, Any]:
    slug = "".join(c if c.isalnum() else "_" for c in tool_name.lower()).strip("_") or "tool"
    return {
        "summary": f"Prepared a no-op adoption stub for {tool_name}.",
        "what_you_get": (
            f"A placeholder module documenting where {tool_name} would plug in. "
            "Run live (with a provider configured) to generate a real change."
        ),
        "files": [
            {
                "path": f"frontier_scout_adoption_{slug}.md",
                "action": "create",
                "contents": (
                    f"# Adoption stub: {tool_name}\n\n"
                    "Generated by `frontier-scout implement --dry-run`. No code "
                    "was modified and no tests were run. Configure a provider "
                    "(Anthropic/OpenAI key, or the Claude/Codex CLI) and re-run "
                    "without --dry-run to generate a real, tested change.\n"
                ),
            }
        ],
        "test_command": "",
    }


# ── LLM change generation ─────────────────────────────────────────────────────


def _repo_context(repo: Path, max_files: int = 60, max_bytes: int = 6000) -> str:
    """Compact repo snapshot for the codegen prompt: tree + a few key files."""
    skip_dirs = {
        ".git", "node_modules", ".venv", "venv", "__pycache__",
        ".scratch", ".mypy_cache", ".pytest_cache", "dist", "build",
    }
    tree: list[str] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        rel_root = Path(root).relative_to(repo)
        for name in sorted(names):
            rel = (rel_root / name).as_posix()
            tree.append(rel)
            if len(tree) >= max_files:
                break
        if len(tree) >= max_files:
            break
    key_files = []
    for name in ("README.md", "pyproject.toml", "requirements.txt", "package.json"):
        f = repo / name
        if f.exists() and f.is_file():
            try:
                key_files.append(f"--- {name} ---\n{f.read_text(errors='ignore')[:max_bytes]}")
            except OSError:
                continue
    return "FILES:\n" + "\n".join(tree) + "\n\n" + "\n\n".join(key_files)


def _generate_change(
    provider: Any, tool_name: str, instruction: str, repo: Path
) -> tuple[dict[str, Any], float]:
    """Ask the LLM for a minimal code change. Returns (change, cost_usd)."""
    from cost_tracker import log_call
    from llm_client import call_with_retry

    from frontier_scout.providers import FAST, first_tool_use

    model_id = provider.model(FAST)
    context = _repo_context(repo)
    user = (
        f"Repository to modify:\n\n{context}\n\n"
        f"TASK: {instruction}\n\n"
        "Emit the minimal code change via `emit_code_change`. Include a test "
        "file or test additions so the change is verifiable. You MUST call the "
        "tool — do not respond with prose only."
    )
    resp = call_with_retry(
        provider,
        "implement-codegen",
        model=model_id,
        max_tokens=_MAX_TOKENS,
        system=(
            "You are Frontier Scout's implementation engine. You make the "
            "smallest correct change that adopts a tool into the user's repo "
            "and proves it with a test. Match the repo's existing style and "
            "test framework. Never invent secrets or absolute paths."
        ),
        tools=[IMPLEMENT_TOOL],
        tool_choice={"type": "tool", "name": "emit_code_change"},
        messages=[{"role": "user", "content": user}],
    )
    cost = log_call("implement-codegen", model_id, resp.usage)
    tool_use = first_tool_use(resp.content)
    if tool_use is None:
        raise RuntimeError("implementation engine returned no structured change")
    return dict(tool_use.input), cost


# ── Public entry point ─────────────────────────────────────────────────────────


def run_implement(
    *,
    repo: Path,
    tool_name: str,
    instruction: str | None = None,
    dry_run: bool = False,
    test_command: str | None = None,
    reporter: Any = None,
    provider: Any = None,
) -> ImplementResult:
    """Generate, apply (in isolation), and test a tool-adoption change."""
    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    repo = repo.resolve()
    instruction = instruction or (
        f"Adopt {tool_name} into this repository with the smallest useful, "
        "tested change."
    )

    # Decide whether we can run live.
    if not dry_run and provider is None:
        try:
            from frontier_scout.providers import resolve_provider

            provider = resolve_provider()
        except Exception:  # noqa: BLE001 — no provider → fall back to dry-run
            dry_run = True

    progress.stage("Generating change")
    cost = 0.0
    if dry_run:
        change = _synthetic_change(tool_name)
    else:
        try:
            change, cost = _generate_change(provider, tool_name, instruction, repo)
        except Exception as exc:  # noqa: BLE001
            return ImplementResult(
                tool_name=tool_name,
                status="error",
                summary="Could not generate a change.",
                what_you_get="",
                repo=str(repo),
                error=str(exc),
                cost_usd=cost,
            )

    progress.stage("Preparing isolated workspace")
    try:
        workspace, is_worktree = _make_workspace(repo)
    except Exception as exc:  # noqa: BLE001
        return ImplementResult(
            tool_name=tool_name,
            status="error",
            summary="Could not stage an isolated workspace.",
            what_you_get="",
            repo=str(repo),
            error=str(exc),
            cost_usd=cost,
        )

    applied = _apply_files(workspace, change.get("files") or [])
    diff = _git_diff(workspace, is_worktree)
    resolved_cmd = (test_command or change.get("test_command") or "").strip()
    if not resolved_cmd:
        resolved_cmd = default_test_command(workspace)

    result = ImplementResult(
        tool_name=tool_name,
        status="prepared",
        summary=str(change.get("summary") or ""),
        what_you_get=str(change.get("what_you_get") or ""),
        files_changed=applied,
        diff=diff,
        test_command=resolved_cmd,
        cost_usd=cost,
        workspace=str(workspace),
        is_worktree=is_worktree,
        repo=str(repo),
    )

    if dry_run:
        progress.log("Dry-run: change prepared, no tests executed.", tone="info")
        _persist(result)
        return result

    progress.stage("Running tests")
    env = _hermetic_env(workspace)
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 — explicit command, hermetic env
            shlex.split(resolved_cmd),
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT,
        )
        result.exit_code = completed.returncode
        result.test_output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        result.status = "passed" if completed.returncode == 0 else "failed"
    except FileNotFoundError as exc:
        result.status = "error"
        result.exit_code = 127
        result.error = f"Test command not found: {exc}"
    except subprocess.TimeoutExpired:
        result.status = "failed"
        result.exit_code = 124
        result.error = f"Tests timed out after {_TIMEOUT}s."
    result.duration_s = int(time.monotonic() - started)

    progress.log(
        f"Implement & Test: {result.status} (exit {result.exit_code})",
        tone="ok" if result.status == "passed" else "warn",
    )
    _persist(result)
    return result


# ── Keep / Discard ─────────────────────────────────────────────────────────────


def keep_changes(result: ImplementResult) -> list[str]:
    """Copy the changed files from the workspace into the real working tree.

    Does NOT commit — the user reviews and commits. Returns the list of repo
    paths written.
    """
    workspace = Path(result.workspace)
    repo = Path(result.repo)
    written: list[str] = []
    for rel in result.files_changed:
        src = workspace / rel
        if not src.exists():
            continue
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(errors="ignore"))
        written.append(rel)
    discard(result)
    return written


def discard(result: ImplementResult) -> None:
    """Tear down the isolated workspace (git worktree or temp copy)."""
    workspace = Path(result.workspace)
    if not workspace.exists():
        return
    if result.is_worktree:
        try:
            subprocess.run(  # noqa: S603 — fixed args, no shell
                ["git", "-C", result.repo, "worktree", "remove", "--force", str(workspace)],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    # Remove the temp parent regardless (covers copy mode + leftover worktree).
    parent = workspace.parent
    if parent.exists() and parent.name.startswith("repo") is False:
        shutil.rmtree(parent, ignore_errors=True)
    elif workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)


# ── Persistence ──────────────────────────────────────────────────────────────


def _persist(result: ImplementResult) -> None:
    """Record the run in the local store + write a receipt. Best-effort."""
    try:
        from frontier_scout.store import (
            create_trial_run,
            finish_trial_run,
            home_dir,
            save_lab_result,
            upsert_tool,
        )

        tool_id = upsert_tool(result.tool_name, category="dev_tool")
        trial_id = create_trial_run(
            tool_id, requested_action=f"implement {result.tool_name}"
        )
        save_lab_result(
            trial_id,
            {
                "runtime": "implement",
                "status": result.status,
                "exit_code": result.exit_code,
                "duration_s": result.duration_s,
                "cost_usd": result.cost_usd,
                "summary": result.summary,
                "test_command": result.test_command,
            },
        )
        finish_trial_run(trial_id, status=result.status, decision="implement")

        receipts = home_dir() / "reports" / "implementations"
        receipts.mkdir(parents=True, exist_ok=True)
        slug = "".join(
            c if c.isalnum() else "-" for c in result.tool_name.lower()
        ).strip("-") or "tool"
        (receipts / f"{slug}.md").write_text(_render_receipt(result))
    except Exception:  # noqa: BLE001 — persistence must never break the run
        pass


def _render_receipt(result: ImplementResult) -> str:
    lines = [
        f"# Implement & Test: {result.tool_name}",
        "",
        f"Repo: {result.repo}",
        f"Status: {result.status}",
        f"Test command: {result.test_command}",
        f"Exit code: {result.exit_code}",
        f"Duration: {result.duration_s}s",
        "Working tree mutated: no (changes staged in an isolated workspace)",
        "",
        "## What you get",
        "",
        result.what_you_get or "(none)",
        "",
        "## Files changed",
        "",
    ]
    for rel in result.files_changed:
        lines.append(f"- {rel}")
    if result.error:
        lines += ["", "## Error", "", result.error]
    return "\n".join(lines).rstrip() + "\n"
