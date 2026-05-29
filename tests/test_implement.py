"""Stream 4 — Implement & Test.

Covers the offline (dry-run) plumbing and the isolation/path-safety
invariants without spending on a live LLM or running the full test runner:

  * dry-run produces a "prepared" result with a synthetic, inert change
  * the real working tree is never mutated unless keep_changes() is called
  * keep_changes() copies staged files into the working tree (no commit)
  * proposed paths that escape the repo root are rejected
  * test-command auto-detection picks the right runner
  * a live change run (LLM stubbed) applies files, runs a real test in the
    isolated copy, and reports pass/fail
"""

from __future__ import annotations

import subprocess
import types
from pathlib import Path

from frontier_scout import implement
from frontier_scout.implement import (
    _apply_files,
    _safe_relpath,
    default_test_command,
    discard,
    keep_changes,
    run_implement,
)


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)


# ── Path safety ──────────────────────────────────────────────────────────────


def test_safe_relpath_accepts_normal():
    assert _safe_relpath("src/app.py") == "src/app.py"
    assert _safe_relpath("tests/test_x.py") == "tests/test_x.py"


def test_safe_relpath_rejects_escape():
    for bad in ("/etc/passwd", "../secret", "a/../../b", "~/x", "C:\\win"):
        assert _safe_relpath(bad) is None, bad
    assert _safe_relpath("") is None


def test_apply_files_jails_paths(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    applied = _apply_files(
        ws,
        [
            {"path": "ok.py", "action": "create", "contents": "x = 1\n"},
            {"path": "../escape.py", "action": "create", "contents": "bad"},
            {"path": "/abs.py", "action": "create", "contents": "bad"},
        ],
    )
    assert applied == ["ok.py"]
    assert (ws / "ok.py").read_text() == "x = 1\n"
    assert not (tmp_path / "escape.py").exists()


# ── Test-command detection ─────────────────────────────────────────────────────


def test_default_test_command(tmp_path):
    assert default_test_command(tmp_path) == "pytest -q"
    (tmp_path / "package.json").write_text("{}")
    assert default_test_command(tmp_path) == "npm test"


def test_default_test_command_makefile(tmp_path):
    (tmp_path / "Makefile").write_text("test:\n\tpytest -q\n")
    assert default_test_command(tmp_path) == "make test"


# ── Dry-run plumbing ───────────────────────────────────────────────────────────


def test_dry_run_prepares_without_mutating(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n")
    before = set(p.name for p in tmp_path.iterdir())
    result = run_implement(repo=tmp_path, tool_name="dspy", dry_run=True)
    assert result.status == "prepared"
    assert result.files_changed  # synthetic stub staged in the workspace
    assert result.cost_usd == 0.0
    # The real working tree is untouched.
    assert set(p.name for p in tmp_path.iterdir()) == before
    discard(result)


def test_keep_copies_into_working_tree(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n")
    result = run_implement(repo=tmp_path, tool_name="dspy", dry_run=True)
    # Force a "passed" so keep_changes proceeds like a real success.
    result.status = "passed"
    written = keep_changes(result)
    assert written
    for rel in written:
        assert (tmp_path / rel).exists()


def test_discard_removes_workspace(tmp_path):
    (tmp_path / "README.md").write_text("# repo\n")
    result = run_implement(repo=tmp_path, tool_name="dspy", dry_run=True)
    ws = Path(result.workspace)
    assert ws.exists()
    discard(result)
    assert not ws.exists()


# ── Live path with a stubbed LLM (no spend, real subprocess) ────────────────────


def test_live_run_applies_and_tests(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "README.md").write_text("# proj\n")
    _git_init(repo)

    change = {
        "summary": "Add a trivial module + passing test.",
        "what_you_get": "A verified hello() function.",
        "files": [
            {"path": "hello.py", "action": "create", "contents": "def hello():\n    return 'hi'\n"},
            {
                "path": "test_hello.py",
                "action": "create",
                "contents": "from hello import hello\n\ndef test_hello():\n    assert hello() == 'hi'\n",
            },
        ],
        "test_command": "python -m pytest -q test_hello.py",
    }
    monkeypatch.setattr(
        implement, "_generate_change", lambda *a, **k: (change, 0.0)
    )

    result = run_implement(
        repo=repo,
        tool_name="hello-lib",
        provider=types.SimpleNamespace(),  # unused — _generate_change is stubbed
    )
    assert result.status == "passed", result.test_output
    assert "hello.py" in result.files_changed
    assert result.is_worktree is True
    assert result.diff  # git diff captured
    # Working tree of the real repo is still clean (no hello.py leaked).
    assert not (repo / "hello.py").exists()
    discard(result)


def test_live_run_reports_failure(tmp_path, monkeypatch):
    repo = tmp_path / "proj2"
    repo.mkdir()
    (repo / "README.md").write_text("# proj2\n")
    _git_init(repo)

    change = {
        "summary": "Add a failing test.",
        "what_you_get": "nothing useful",
        "files": [
            {
                "path": "test_fail.py",
                "action": "create",
                "contents": "def test_fail():\n    assert False\n",
            }
        ],
        "test_command": "python -m pytest -q test_fail.py",
    }
    monkeypatch.setattr(implement, "_generate_change", lambda *a, **k: (change, 0.0))
    result = run_implement(
        repo=repo, tool_name="bad-lib", provider=types.SimpleNamespace()
    )
    assert result.status == "failed"
    assert result.exit_code != 0
    discard(result)


def test_codegen_error_returns_error_status(tmp_path, monkeypatch):
    repo = tmp_path / "proj3"
    repo.mkdir()
    (repo / "README.md").write_text("# p\n")

    def _boom(*a, **k):
        raise RuntimeError("no tool call")

    monkeypatch.setattr(implement, "_generate_change", _boom)
    result = run_implement(
        repo=repo, tool_name="x", provider=types.SimpleNamespace()
    )
    assert result.status == "error"
    assert "no tool call" in result.error


def test_no_files_applied_fails_fast(tmp_path, monkeypatch):
    """A change whose every path is rejected by the safety jail must NOT
    report success with zero mutation — it must surface an error."""

    repo = tmp_path / "proj4"
    repo.mkdir()
    (repo / "README.md").write_text("# p\n")
    _git_init(repo)

    # Every proposed path escapes the workspace → all rejected.
    change = {
        "summary": "Escapes only.",
        "what_you_get": "nothing",
        "files": [
            {"path": "/etc/passwd", "action": "create", "contents": "x"},
            {"path": "../../escape.py", "action": "create", "contents": "y"},
        ],
        "test_command": "true",
    }
    monkeypatch.setattr(implement, "_generate_change", lambda *a, **k: (change, 0.0))
    result = run_implement(
        repo=repo, tool_name="evil", provider=types.SimpleNamespace()
    )
    assert result.status == "error"
    assert "no file" in (result.summary + result.error).lower()
    # And the real tree is untouched.
    assert not (repo / "escape.py").exists()


def test_discard_only_removes_prefixed_temp_dir(tmp_path):
    """discard() must never rmtree an arbitrary parent — only our own
    prefixed temp dir. A malformed workspace path is a no-op."""

    from frontier_scout.implement import _WORKSPACE_PREFIX, ImplementResult

    # A workspace path NOT under our prefix must be left completely alone.
    victim = tmp_path / "precious"
    victim.mkdir()
    (victim / "keepme.txt").write_text("do not delete")
    bogus = ImplementResult(
        tool_name="t",
        status="error",
        summary="x",
        what_you_get="",
        workspace=str(victim / "repo"),
        is_worktree=False,
        repo=str(tmp_path),
    )
    discard(bogus)
    assert victim.exists()
    assert (victim / "keepme.txt").exists()
    assert _WORKSPACE_PREFIX  # sanity: constant is defined


def test_keep_with_failed_status_still_discards(tmp_path, monkeypatch):
    """CLI contract: --keep on a non-passed run must still tear down the
    isolated workspace (no temp-dir leak)."""

    repo = tmp_path / "proj5"
    repo.mkdir()
    (repo / "README.md").write_text("# p\n")
    _git_init(repo)

    change = {
        "summary": "Failing change.",
        "what_you_get": "nope",
        "files": [
            {"path": "test_x.py", "action": "create", "contents": "def test_x():\n    assert False\n"}
        ],
        "test_command": "python -m pytest -q test_x.py",
    }
    monkeypatch.setattr(implement, "_generate_change", lambda *a, **k: (change, 0.0))
    result = run_implement(repo=repo, tool_name="bad", provider=types.SimpleNamespace())
    assert result.status == "failed"
    # Simulate the CLI's keep+failed branch: it falls through to discard().
    discard(result)
    assert not Path(result.workspace).parent.exists()
