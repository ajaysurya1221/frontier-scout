# tests/test_dogfood_policy.py
"""The repo dogfoods its own policy: `frontier-scout.policy.json` must stay loadable,
compile cleanly, and make the decisions the repo's own governance depends on. If a
future edit breaks the committed policy, this fails before it reaches a real session."""
import json
from pathlib import Path

from frontier_scout.agent_firewall import hook_runtime as hr
from frontier_scout.agent_firewall.lock import policy_hash
from frontier_scout.agent_firewall.policy import load_policy

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_FILE = REPO_ROOT / "frontier-scout.policy.json"


def _policy_dict():
    return json.loads(POLICY_FILE.read_text())


def test_committed_policy_loads_clean():
    policy, warnings = load_policy(str(POLICY_FILE))
    assert warnings == []  # a well-formed, fail-open-free policy
    assert "gitnexus" in policy.mcp_server_allowlist


def test_committed_lock_matches_policy_if_present():
    lock = REPO_ROOT / "policy.lock.json"
    if not lock.exists():
        return
    assert json.loads(lock.read_text())["policy_sha256"] == policy_hash(_policy_dict())


def test_dogfood_decisions_protect_the_repo():
    p = _policy_dict()
    assert hr.decide("Bash", {"command": "rm -rf /tmp/x"}, p)[0] == "deny"
    assert hr.decide("Bash", {"command": "git push --force"}, p)[0] == "deny"
    assert hr.decide("Bash", {"command": "pytest -q"}, p)[0] == "allow"
    assert hr.decide("Bash", {"command": "git push origin main"}, p)[0] == "allow"
    assert hr.decide("Edit", {"file_path": "frontier_scout/agent_firewall/compile.py"}, p)[0] == "allow"
    # CI config + the guardrails themselves are approval-gated, not silently editable.
    assert hr.decide("Edit", {"file_path": ".github/workflows/ci.yml"}, p)[0] == "ask"
    assert hr.decide("Edit", {"file_path": "frontier-scout.policy.json"}, p)[0] == "ask"
    # MCP is deny-by-default off the allowlist; gitnexus (the repo's code-intel server) is allowed.
    assert hr.decide("mcp__gitnexus__impact", {}, p)[0] == "allow"
    assert hr.decide("mcp__context7__query", {}, p)[0] == "deny"


def test_eval_substring_is_not_blocked():
    """Regression: 'eval' must NOT be a blocked substring (it would deny `pytest
    tests/test_eval*` and anything containing 'eval')."""
    p = _policy_dict()
    assert hr.decide("Bash", {"command": "pytest tests/test_evaluate_thing.py"}, p)[0] == "allow"
