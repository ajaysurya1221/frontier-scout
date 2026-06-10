# tests/test_agent_cli_compile_verify.py
"""End-to-end CLI: compile -> (run agent) -> open PR -> verify-pr, through main()."""
import json
import os
import subprocess

from frontier_scout.agent_firewall.lock import read_lock
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.agent_firewall.policy import save_policy
from frontier_scout.cli import main

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "PATH": os.environ.get("PATH", ""),
}


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=_ENV)


def _rev(repo, ref="HEAD"):
    return subprocess.run(["git", "-C", repo, "rev-parse", ref], capture_output=True,
                          text=True, env=_ENV).stdout.strip()


def test_compile_cli_writes_artifacts(tmp_path):
    repo = str(tmp_path)
    save_policy(AgentPolicy(allowed_file_globs=["src/**"]), str(tmp_path / "frontier-scout.policy.json"))
    assert main(["agent", "compile", "--repo", repo]) == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".claude" / "hooks" / "_fs_guard.py").exists()
    assert (tmp_path / "policy.lock.json").exists()
    assert (tmp_path / ".github" / "workflows" / "frontier-scout-verify.yml").exists()


def test_compile_cli_generates_policy_when_absent(tmp_path, capsys):
    repo = str(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    assert main(["agent", "compile", "--repo", repo]) == 0
    assert "generated a conservative one" in capsys.readouterr().out
    assert (tmp_path / "frontier-scout.policy.json").exists()


def test_export_claude_prints_deprecation_note(tmp_path, capsys):
    repo = str(tmp_path)
    save_policy(AgentPolicy(), str(tmp_path / "frontier-scout.policy.json"))
    assert main(["agent", "export", "claude", "--repo", repo, "--target", repo]) == 0
    assert "agent compile" in capsys.readouterr().out


def test_verify_pr_cli_fails_closed_then_passes_with_receipt(tmp_path):
    repo = str(tmp_path)
    save_policy(
        AgentPolicy(protected_file_globs=["**/migrations/**"], allowed_file_globs=["src/**"]),
        str(tmp_path / "frontier-scout.policy.json"),
    )
    assert main(["agent", "compile", "--repo", repo]) == 0

    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base (compiled controls)")
    base = _rev(repo)

    # A PR that touches a protected path.
    (tmp_path / "app" / "migrations").mkdir(parents=True)
    (tmp_path / "app" / "migrations" / "0001_init.py").write_text("# schema change\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add migration")

    # No receipts -> protected change is unproven -> fail-closed.
    assert main(["agent", "verify-pr", "--repo", repo, "--base", base]) == 1

    # Add an approving action receipt (uncommitted; read from the working tree).
    ph = read_lock(str(tmp_path / "policy.lock.json"))["policy_sha256"]
    recdir = tmp_path / "frontier-scout-receipts"
    recdir.mkdir()
    (recdir / "r1.json").write_text(json.dumps({
        "receipt_id": "r1", "kind": "agent-action", "policy_hash": ph,
        "tool_name": "Edit", "decision": "ask", "verdict": "needs_approval",
        "files_considered": ["app/migrations/0001_init.py"],
    }))
    assert main(["agent", "verify-pr", "--repo", repo, "--base", base]) == 0


def test_verify_pr_cli_json_output(tmp_path, capsys):
    repo = str(tmp_path)
    save_policy(AgentPolicy(allowed_file_globs=["src/**"]), str(tmp_path / "frontier-scout.policy.json"))
    main(["agent", "compile", "--repo", repo])
    capsys.readouterr()  # drain the compile output
    rc = main(["agent", "verify-pr", "--repo", repo, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "ok" in payload and "summary" in payload
    assert rc == 0


def test_verify_pr_cli_json_out_writes_file_and_keeps_stdout(tmp_path, capsys):
    repo = str(tmp_path)
    save_policy(
        AgentPolicy(protected_file_globs=["**/migrations/**"], allowed_file_globs=["src/**"]),
        str(tmp_path / "frontier-scout.policy.json"),
    )
    main(["agent", "compile", "--repo", repo])
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _rev(repo)
    (tmp_path / "app" / "migrations").mkdir(parents=True)
    (tmp_path / "app" / "migrations" / "0001_init.py").write_text("# schema change\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add migration")
    capsys.readouterr()  # drain

    out_file = tmp_path / "evidence" / "e.json"
    rc = main(["agent", "verify-pr", "--repo", repo, "--base", base, "--json-out", str(out_file)])
    stdout = capsys.readouterr().out
    # Exit code and stdout (annotations + summary) are unchanged by --json-out.
    assert rc == 1
    assert "::error" in stdout
    assert "FAIL" in stdout
    payload = json.loads(out_file.read_text())
    assert payload["ok"] is False
    assert payload["advisory"] is False


def test_verify_pr_cli_json_and_json_out_together(tmp_path, capsys):
    repo = str(tmp_path)
    save_policy(AgentPolicy(allowed_file_globs=["src/**"]), str(tmp_path / "frontier-scout.policy.json"))
    main(["agent", "compile", "--repo", repo])
    capsys.readouterr()  # drain
    out_file = tmp_path / "e.json"
    rc = main(["agent", "verify-pr", "--repo", repo, "--json", "--json-out", str(out_file)])
    stdout_payload = json.loads(capsys.readouterr().out)  # stdout stays pure JSON
    file_payload = json.loads(out_file.read_text())
    assert stdout_payload["ok"] == file_payload["ok"]
    assert rc == 0
