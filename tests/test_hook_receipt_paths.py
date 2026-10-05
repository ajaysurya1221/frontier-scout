# tests/test_hook_receipt_paths.py
"""Receipts must name files the way ``git diff --name-only`` does: repo-relative, POSIX.

Claude Code sends absolute ``file_path`` values. Before this fix a receipt written by the
real hook could never cover a changed path, so every protected change failed closed in CI.
"""

import json
import subprocess

from frontier_scout.agent_firewall import hook_runtime as hr
from frontier_scout.agent_firewall.compile import compile_claude
from frontier_scout.agent_firewall.lock import read_lock
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.agent_firewall.verify import verify_pr


def _policy():
    return AgentPolicy(
        allowed_file_globs=["src/**", "tests/**"],
        protected_file_globs=["**/migrations/**", ".github/workflows/**"],
        allowed_shell_commands=["pytest"],
        mcp_server_allowlist=["github"],
    )


def _compiled(repo):
    out = compile_claude(_policy(), repo=str(repo))
    policy = json.loads((repo / "frontier-scout.policy.json").read_text())
    return policy, read_lock(out["lock"])["policy_sha256"]


def _edit_event(path):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(path), "old_string": "x = 1", "new_string": "x = 2"},
        "session_id": "sess-1",
        "cwd": ".",
    }


def test_repo_relative_inside_outside_and_relative(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app" / "migrations").mkdir(parents=True)
    inside = repo / "app" / "migrations" / "0001_init.py"
    assert hr.repo_relative(str(inside), str(repo)) == "app/migrations/0001_init.py"
    assert hr.repo_relative("app/./migrations/0001_init.py", str(repo)) == "app/migrations/0001_init.py"
    outside = tmp_path / "elsewhere" / "x.py"
    assert hr.repo_relative(str(outside), str(repo)) == str(outside)
    assert hr.repo_relative("", str(repo)) == ""


def test_hook_receipts_record_repo_relative_paths(tmp_path):
    policy, ph = _compiled(tmp_path)
    event = _edit_event(tmp_path / "app" / "migrations" / "0001_init.py")
    hr.handle_pre_tool_use(event, policy=policy, policy_hash=ph, repo=str(tmp_path))
    hr.handle_post_tool_use(event, policy_hash=ph, repo=str(tmp_path))
    written = sorted((tmp_path / ".frontier-scout" / "receipts").glob("*.json"))
    assert len(written) == 2
    for receipt in written:
        assert json.loads(receipt.read_text())["files_considered"] == ["app/migrations/0001_init.py"]


def test_end_to_end_hook_receipt_is_matched_by_verify_pr(tmp_path):
    """Real hook (absolute path) -> receipt on disk -> real git diff -> verify_pr matches it."""
    repo = tmp_path

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("-c", "init.defaultBranch=main", "init", "-q")
    git("config", "user.email", "hook@example.com")
    git("config", "user.name", "hook test")
    policy, ph = _compiled(repo)
    (repo / ".gitignore").write_text(".frontier-scout/\n")
    target = repo / "app" / "migrations" / "0001_init.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")

    # The agent edits a protected file; Claude Code reports the absolute path.
    event = _edit_event(target)
    hr.handle_pre_tool_use(event, policy=policy, policy_hash=ph, repo=str(repo))
    target.write_text("x = 2\n")
    hr.handle_post_tool_use(event, policy_hash=ph, repo=str(repo))
    git("add", "-A")
    git("commit", "-q", "-m", "migration")

    # The hook's repo-relative receipt matches the changed path: the verifier sees the
    # receipt (APPROVAL_UNAUTHENTICATED, not PROTECTED_NO_RECEIPT), but an unsigned receipt
    # cannot authenticate the approval, so a protected change is UNVERIFIED, never PASS.
    res = verify_pr(str(repo), base=base)
    assert res.ok is False and res.verdict == "unverified"
    assert res.reason_codes == ["APPROVAL_UNAUTHENTICATED"]
    assert res.scope == "verified"

    # The same diff with no receipts fails closed.
    res_without = verify_pr(str(repo), base=base, receipts=[])
    assert res_without.ok is False and res_without.verdict == "fail"
    assert any("migrations" in v for v in res_without.violations)
    assert "PROTECTED_NO_RECEIPT" in res_without.reason_codes


def test_verify_pr_accepts_receipts_written_with_absolute_paths(tmp_path):
    """Receipts from hooks compiled before the path fix still match the changed path."""
    _, ph = _compiled(tmp_path)
    receipt = {
        "receipt_id": "r1",
        "kind": "agent-action",
        "policy_hash": ph,
        "tool_name": "Edit",
        "decision": "ask",
        "verdict": "needs_approval",
        "files_considered": [str(tmp_path / "app" / "migrations" / "0001.py")],
    }
    res = verify_pr(str(tmp_path), changed_files=["app/migrations/0001.py"], receipts=[receipt])
    # Matched (not PROTECTED_NO_RECEIPT), but still not an authenticated approval.
    assert "PROTECTED_NO_RECEIPT" not in res.reason_codes
    assert "APPROVAL_UNAUTHENTICATED" in res.reason_codes
    assert res.ok is False
