"""Codex finding #6 — dependency-trial receipts now report what happened.

Before v1.2.1, a non-dry-run trial wrote ``status = "completed"``,
``exit_code = 0`` even though it never invoked a subprocess. Receipts
were a lie. These tests pin the honest behaviour:

- ``dry_run=True`` → status ``"prepared"``, no subprocess.
- ``dry_run=False`` with no resolvable test command → ``"prepared"``.
- ``dry_run=False`` with a resolvable command → executed; status is
  ``"passed"`` (exit 0) or ``"failed"`` (non-zero); hermetic env (no
  ANTHROPIC_API_KEY etc. leaks).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from frontier_scout.dep_trial import run_dependency_trial


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("requests==2.31.0\n")
    return repo


def test_dry_run_status_is_prepared(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=True,
    )
    assert result["lab_result"]["status"] == "prepared"
    assert result["lab_result"]["exit_code"] == 0


def test_dry_run_never_invokes_subprocess(tmp_path, monkeypatch):
    """If we touch subprocess in dry-run, blow up loudly."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path)

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called in dry-run")

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _boom)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=True,
    )
    assert result["lab_result"]["status"] == "prepared"


def test_executed_trial_records_passed_on_zero_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _fake_run)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=False,
        test_command="pytest -q",
    )
    assert result["lab_result"]["status"] == "passed"
    assert result["lab_result"]["exit_code"] == 0
    assert captured["cmd"] == ["pytest", "-q"]


def test_executed_trial_records_failed_on_non_zero_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path)

    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _fake_run)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=False,
        test_command="pytest -q",
    )
    assert result["lab_result"]["status"] == "failed"
    assert result["lab_result"]["exit_code"] == 1


def test_executed_trial_uses_hermetic_env(tmp_path, monkeypatch):
    """The subprocess must NOT see ANTHROPIC_API_KEY or the real HOME."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak-canary")
    monkeypatch.setenv("HOME", "/Users/should-not-leak")
    repo = _seed_repo(tmp_path)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _fake_run)
    run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=False,
        test_command="pytest -q",
    )
    env = captured["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert env["HOME"] != "/Users/should-not-leak"
    assert env["PIP_CONFIG_FILE"] in ("/dev/null", "nul")  # nul on Windows
    # cwd is the temp dir (not the user's repo).
    assert captured["cwd"] != str(repo.resolve())


def test_executed_trial_handles_missing_command(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = _seed_repo(tmp_path)

    def _fake_run(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file", cmd[0])

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _fake_run)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=False,
        test_command="this-binary-does-not-exist",
    )
    assert result["lab_result"]["status"] == "failed"
    assert result["lab_result"]["exit_code"] == 127


def test_no_resolvable_command_stays_prepared(tmp_path, monkeypatch):
    """Empty repo with no python/node manifest → status prepared, not lie."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "empty-repo"
    repo.mkdir()

    # Patch _default_test_command to return empty string → no default exists.
    monkeypatch.setattr(
        "frontier_scout.dep_trial._default_test_command",
        lambda _repo: "",
    )

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called without command")

    monkeypatch.setattr("frontier_scout.dep_trial.subprocess.run", _boom)
    result = run_dependency_trial(
        "requests",
        from_version="2.31.0",
        to_version="2.32.0",
        repo=repo,
        dry_run=False,
        test_command=None,
    )
    assert result["lab_result"]["status"] == "prepared"
