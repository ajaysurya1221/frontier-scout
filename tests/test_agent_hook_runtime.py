# tests/test_agent_hook_runtime.py
"""The native hook runtime must be self-contained (stdlib only) and fail-closed."""
import json
from pathlib import Path

from frontier_scout.agent_firewall import hook_runtime as hr

POLICY = {
    "version": 1,
    "allowed_tools": [],
    "blocked_tools": ["WebSearch"],
    "allowed_shell_commands": ["pytest", "git status"],
    "blocked_shell_commands": ["rm -rf", "git push --force"],
    "allowed_file_globs": ["src/**", "tests/**"],
    "protected_file_globs": ["**/migrations/**", ".github/workflows/**"],
    "mcp_server_allowlist": ["github"],
    "required_checks": ["pytest"],
    "approval_gates": ["network", "shell"],
    "policy_notes": "",
}


# --- decide() : structured tool-call decisions -----------------------------------

def test_decide_denies_blocked_shell():
    decision, _ = hr.decide("Bash", {"command": "rm -rf /tmp/x"}, POLICY)
    assert decision == "deny"


def test_decide_allows_allowlisted_shell():
    decision, _ = hr.decide("Bash", {"command": "pytest -q"}, POLICY)
    assert decision == "allow"


def test_decide_asks_unknown_shell_fail_closed():
    decision, _ = hr.decide("Bash", {"command": "curl https://evil.example"}, POLICY)
    assert decision == "ask"


def test_decide_asks_protected_write():
    decision, _ = hr.decide("Edit", {"file_path": "app/migrations/0001_init.py"}, POLICY)
    assert decision == "ask"


def test_decide_allows_write_within_allowed_globs():
    decision, _ = hr.decide("Write", {"file_path": "src/pkg/a.py"}, POLICY)
    assert decision == "allow"


def test_decide_asks_write_outside_any_glob_fail_closed():
    decision, _ = hr.decide("Write", {"file_path": "random/place.py"}, POLICY)
    assert decision == "ask"


def test_decide_denies_off_allowlist_mcp():
    decision, _ = hr.decide("mcp__evilserver__exfiltrate", {}, POLICY)
    assert decision == "deny"


def test_decide_allows_allowlisted_mcp():
    decision, _ = hr.decide("mcp__github__create_issue", {"title": "x"}, POLICY)
    assert decision == "allow"


def test_decide_denies_blocked_tool():
    decision, _ = hr.decide("WebSearch", {"query": "x"}, POLICY)
    assert decision == "deny"


def test_decide_asks_network_fetch():
    decision, _ = hr.decide("WebFetch", {"url": "https://api.example.com"}, POLICY)
    assert decision == "ask"


def test_decide_allows_read():
    decision, _ = hr.decide("Read", {"file_path": "anything"}, POLICY)
    assert decision == "allow"


def test_decide_unknown_tool_fail_closed():
    decision, _ = hr.decide("SomeFutureTool", {}, POLICY)
    assert decision == "ask"


# --- handle_pre_tool_use() : decision JSON + receipt write ------------------------

def _pre_event(tool_name, tool_input):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "session_id": "sess-1",
        "cwd": ".",
    }


def test_handle_pre_returns_claude_decision_shape(tmp_path):
    out = hr.handle_pre_tool_use(
        _pre_event("Bash", {"command": "pytest -q"}),
        policy=POLICY, policy_hash="abc123", repo=str(tmp_path),
    )
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "allow"
    assert "permissionDecisionReason" in hso


def test_handle_pre_writes_action_receipt(tmp_path):
    repo = str(tmp_path)
    hr.handle_pre_tool_use(
        _pre_event("Edit", {"file_path": "app/migrations/0001.py"}),
        policy=POLICY, policy_hash="lockhash", repo=repo,
    )
    files = list((Path(repo) / ".frontier-scout" / "receipts").glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text())
    assert rec["kind"] == "agent-action"
    assert rec["policy_hash"] == "lockhash"
    assert rec["tool_name"] == "Edit"
    assert rec["decision"] == "ask"
    assert rec["verdict"] == "needs_approval"
    assert "app/migrations/0001.py" in rec["files_considered"]


def test_pre_receipt_redacts_secrets(tmp_path):
    repo = str(tmp_path)
    hr.handle_pre_tool_use(
        _pre_event("Bash", {"command": "echo sk-ant-PLANTEDSECRETVALUE12345"}),
        policy=POLICY, policy_hash="h", repo=repo,
    )
    blob = (list((Path(repo) / ".frontier-scout" / "receipts").glob("*.json"))[0]).read_text()
    assert "PLANTEDSECRETVALUE12345" not in blob


def test_handle_post_writes_realized_receipt(tmp_path):
    repo = str(tmp_path)
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/a.py"},
        "tool_output": {"status": "success"},
    }
    hr.handle_post_tool_use(event, policy_hash="h", repo=repo)
    rec = json.loads((list((Path(repo) / ".frontier-scout" / "receipts").glob("*.json"))[0]).read_text())
    assert rec["kind"] == "agent-action"
    assert rec["realized"] is not None
    assert "src/a.py" in rec["files_considered"]


def test_hook_receipt_validates_against_pydantic_receipt_model(tmp_path):
    """The stdlib hook writes raw JSON; it must still satisfy the canonical schema
    so `agent receipts` and the verifier can read both kinds uniformly."""
    from frontier_scout.agent_firewall.models import Receipt

    repo = str(tmp_path)
    hr.handle_pre_tool_use(
        _pre_event("Bash", {"command": "pytest -q"}),
        policy=POLICY, policy_hash="h", repo=repo,
    )
    raw = json.loads((list((Path(repo) / ".frontier-scout" / "receipts").glob("*.json"))[0]).read_text())
    Receipt.model_validate(raw)  # raises on drift


def test_hook_runtime_is_stdlib_only():
    """The module is copied verbatim into a user's .claude/hooks/, so it must not
    import anything from frontier_scout (it would not be importable there)."""
    src = Path(hr.__file__).read_text()
    assert "import frontier_scout" not in src
    assert "from frontier_scout" not in src
