# tests/test_agent_compile.py
import json
import subprocess
import sys
from pathlib import Path

from frontier_scout.agent_firewall.compile import compile_claude
from frontier_scout.agent_firewall.lock import policy_hash
from frontier_scout.agent_firewall.models import AgentPolicy


def _policy():
    return AgentPolicy(
        blocked_shell_commands=["rm -rf", "git push --force"],
        allowed_shell_commands=["pytest", "git status"],
        blocked_tools=["WebSearch"],
        allowed_file_globs=["src/**", "tests/**"],
        protected_file_globs=["**/migrations/**", ".github/workflows/**"],
        mcp_server_allowlist=["github"],
        required_checks=["pytest"],
        approval_gates=["network", "shell"],
    )


def test_compile_writes_all_artifacts(tmp_path):
    repo = str(tmp_path)
    out = compile_claude(_policy(), repo=repo)
    for key in ("settings", "pre_hook", "post_hook", "guard", "lock", "workflow", "managed", "policy"):
        assert key in out, key
        assert Path(out[key]).exists(), key
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".claude" / "hooks" / "_fs_guard.py").exists()
    assert (tmp_path / ".claude" / "hooks" / "pre_tool_use.py").exists()
    assert (tmp_path / ".claude" / "hooks" / "post_tool_use.py").exists()
    assert (tmp_path / "policy.lock.json").exists()
    assert (tmp_path / ".github" / "workflows" / "frontier-scout-verify.yml").exists()


def test_compiled_settings_permissions_translate_policy(tmp_path):
    compile_claude(_policy(), repo=str(tmp_path))
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    perms = settings["permissions"]
    assert "Bash(rm -rf:*)" in perms["deny"]
    assert "WebSearch" in perms["deny"]
    assert "Bash(pytest:*)" in perms["allow"]
    assert "mcp__github__*" in perms["allow"]
    # protected globs are ASK (human approval), not hard deny
    assert any("migrations" in r for r in perms["ask"])
    assert any("src/**" in r for r in perms["allow"])


def test_compiled_settings_wire_both_hooks(tmp_path):
    compile_claude(_policy(), repo=str(tmp_path))
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "PreToolUse" in settings["hooks"]
    assert "PostToolUse" in settings["hooks"]
    pre_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "pre_tool_use.py" in pre_cmd


def test_guard_is_verbatim_copy_of_hook_runtime(tmp_path):
    compile_claude(_policy(), repo=str(tmp_path))
    from frontier_scout.agent_firewall import hook_runtime
    guard_src = (tmp_path / ".claude" / "hooks" / "_fs_guard.py").read_text()
    assert guard_src == Path(hook_runtime.__file__).read_text()


def test_generated_guard_uses_structural_bash_matcher(tmp_path):
    """The generated hook must carry the structural matcher (shlex + command units),
    not the old raw-substring deny."""
    compile_claude(_policy(), repo=str(tmp_path))
    guard_src = (tmp_path / ".claude" / "hooks" / "_fs_guard.py").read_text()
    assert "import shlex" in guard_src
    assert "_resolve_units" in guard_src and "_blocked_hit" in guard_src


def test_lock_binds_the_compiled_policy(tmp_path):
    p = _policy()
    compile_claude(p, repo=str(tmp_path))
    lock = json.loads((tmp_path / "policy.lock.json").read_text())
    # the lock hashes the policy file that was actually written
    written = json.loads((tmp_path / "frontier-scout.policy.json").read_text())
    assert lock["policy_sha256"] == policy_hash(written)
    assert lock["targets"] == ["claude"]


def test_managed_settings_from_allowlist(tmp_path):
    compile_claude(_policy(), repo=str(tmp_path))
    managed = json.loads((tmp_path / "managed-settings.json").read_text())
    assert {"serverName": "github"} in managed["allowedMcpServers"]


def test_generated_hook_runs_standalone_and_denies(tmp_path):
    """The generated pre-hook + _fs_guard must work as a subprocess with no
    frontier_scout on the path (proving the copied guard is self-contained)."""
    compile_claude(_policy(), repo=str(tmp_path))
    event = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "rm -rf /tmp/x"}})
    proc = subprocess.run(
        [sys.executable, str(tmp_path / ".claude" / "hooks" / "pre_tool_use.py")],
        input=event, capture_output=True, text=True,
        cwd=str(tmp_path), env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    receipts = list((tmp_path / ".frontier-scout" / "receipts").glob("*.json"))
    assert len(receipts) == 1
