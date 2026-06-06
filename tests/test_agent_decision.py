# tests/test_agent_decision.py
from frontier_scout.agent_firewall.decision import evaluate_task
from frontier_scout.agent_firewall.models import ScanResult
from frontier_scout.agent_firewall.policy import generate_policy


def _policy():
    return generate_policy(ScanResult(repo=".", detected_checks=["pytest"]))


def test_read_only_task_is_allowed():
    d = evaluate_task("list the files and read the README", _policy())
    assert d.verdict == "allow"
    assert d.static_only is True


def test_blocked_shell_command_is_blocked():
    d = evaluate_task("run rm -rf / to clean up", _policy())
    assert d.verdict == "block"
    assert any(r.rule_id == "shell.blocked" for r in d.reasons)


def test_protected_path_change_needs_approval():
    d = evaluate_task("update the schema",
                      _policy(), changed_files=["migrations/0002_add.sql"])
    assert d.verdict == "needs_approval"
    assert any(r.rule_id == "path.protected" for r in d.reasons)


def test_credential_capability_needs_approval():
    d = evaluate_task("read the AWS secret key from the environment and use it", _policy())
    assert d.verdict in ("needs_approval", "block")
    assert "credential" in d.dangerous_flags or any(
        "credential" in r.rule_id for r in d.reasons)


def test_required_checks_are_surfaced():
    d = evaluate_task("read a file", _policy())
    assert "pytest" in d.required_checks


def test_evaluate_task_never_spawns_a_subprocess(monkeypatch):
    import subprocess
    def _boom(*a, **k):
        raise AssertionError("evaluate_task must not execute anything")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    evaluate_task("deploy to production and run the migration", _policy(),
                  changed_files=["infra/main.tf"])
