# tests/test_agent_verify_pr.py
import subprocess

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


def _setup(tmp_path):
    out = compile_claude(_policy(), repo=str(tmp_path))
    return str(tmp_path), read_lock(out["lock"])["policy_sha256"]


def _receipt(ph, *, tool, files, decision="allow", rid="r1"):
    return {
        "receipt_id": rid, "kind": "agent-action", "policy_hash": ph,
        "tool_name": tool, "decision": decision, "files_considered": files,
        "verdict": {"allow": "allow", "ask": "needs_approval", "deny": "block"}[decision],
    }


def test_clean_allowed_change_with_receipt_passes(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["src/a.py"],
                    receipts=[_receipt(ph, tool="Write", files=["src/a.py"])])
    assert res.ok is True
    assert res.violations == []


def test_protected_change_without_receipt_fails_closed(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["app/migrations/0001.py"], receipts=[])
    assert res.ok is False
    assert any("migrations" in v for v in res.violations)


def test_protected_change_with_approving_receipt_passes(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(
        repo, changed_files=["app/migrations/0001.py"],
        receipts=[_receipt(ph, tool="Edit", files=["app/migrations/0001.py"], decision="ask")],
    )
    assert res.ok is True


def test_allowed_change_without_receipts_warns_but_passes(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["src/a.py"], receipts=[])
    assert res.ok is True
    assert res.warnings  # "hooks may not be installed" signal


def test_stale_receipt_policy_hash_mismatch_fails(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["src/a.py"],
                    receipts=[_receipt("WRONGHASH", tool="Write", files=["src/a.py"])])
    assert res.ok is False
    assert any("policy" in v.lower() for v in res.violations)


def test_denied_action_that_changed_file_fails(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(
        repo, changed_files=["src/a.py"],
        receipts=[_receipt(ph, tool="Write", files=["src/a.py"], decision="deny")],
    )
    assert res.ok is False
    assert any("deny" in v.lower() or "bypass" in v.lower() for v in res.violations)


def test_policy_drift_since_compile_fails(tmp_path):
    repo, ph = _setup(tmp_path)
    # tamper with the policy file out of band
    (tmp_path / "frontier-scout.policy.json").write_text('{"version": 1, "allowed_tools": ["Everything"]}')
    res = verify_pr(repo, changed_files=["src/a.py"],
                    receipts=[_receipt(ph, tool="Write", files=["src/a.py"])])
    assert res.ok is False
    assert any("drift" in v.lower() or "lock" in v.lower() for v in res.violations)


def test_missing_lock_fails(tmp_path):
    res = verify_pr(str(tmp_path), changed_files=["src/a.py"], receipts=[])
    assert res.ok is False
    assert any("compile" in v.lower() or "lock" in v.lower() for v in res.violations)


def test_advisory_mode_downgrades_violations_to_warnings(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["app/migrations/0001.py"], receipts=[], advisory=True)
    assert res.ok is True
    assert res.warnings


def test_annotations_use_github_format(tmp_path):
    repo, ph = _setup(tmp_path)
    res = verify_pr(repo, changed_files=["app/migrations/0001.py"], receipts=[])
    assert any(a.startswith("::error") for a in res.annotations)


def test_git_diff_names_reads_real_repo(tmp_path):
    from frontier_scout.agent_firewall.verify import git_diff_names

    repo = str(tmp_path)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ.get("PATH", "")}

    def git(*args):
        subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)

    git("init", "-q")
    (tmp_path / "base.txt").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True, env=env).stdout.strip()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "feature.py").write_text("y")
    git("add", "-A")
    git("commit", "-q", "-m", "feature")
    names = git_diff_names(repo, base)
    assert "src/feature.py" in names
