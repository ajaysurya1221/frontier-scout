# tests/test_agent_lock.py
from frontier_scout.agent_firewall.lock import (
    default_lock_path,
    policy_hash,
    read_lock,
    write_lock,
)
from frontier_scout.agent_firewall.models import AgentPolicy


def test_policy_hash_is_stable_across_equivalent_dumps():
    p = AgentPolicy(blocked_shell_commands=["rm -rf"], approval_gates=["shell"])
    again = AgentPolicy.model_validate(p.model_dump())
    assert policy_hash(p) == policy_hash(again)


def test_policy_hash_accepts_dict_or_model():
    p = AgentPolicy(allowed_shell_commands=["pytest"])
    assert policy_hash(p) == policy_hash(p.model_dump())


def test_policy_hash_changes_when_policy_changes():
    a = AgentPolicy(allowed_shell_commands=["pytest"])
    b = AgentPolicy(allowed_shell_commands=["pytest", "ruff"])
    assert policy_hash(a) != policy_hash(b)


def test_policy_hash_is_hex_sha256():
    h = policy_hash(AgentPolicy())
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_write_then_read_lock(tmp_path):
    repo = str(tmp_path)
    p = AgentPolicy(blocked_shell_commands=["rm -rf"])
    path = write_lock(p, repo, targets=["claude"])
    assert path == default_lock_path(repo)
    lock = read_lock(path)
    assert lock is not None
    assert lock["policy_sha256"] == policy_hash(p)
    assert lock["targets"] == ["claude"]
    assert lock["frontier_scout_version"]
    assert "compiled_at" in lock


def test_read_lock_missing_returns_none(tmp_path):
    assert read_lock(default_lock_path(str(tmp_path))) is None
