# tests/test_agent_policy.py

from frontier_scout.agent_firewall.models import AgentPolicy, RiskSurface, ScanResult
from frontier_scout.agent_firewall.policy import (
    default_policy_path,
    explain_policy,
    generate_policy,
    load_policy,
    save_policy,
)


def _scan() -> ScanResult:
    return ScanResult(
        repo=".",
        surfaces=[
            RiskSurface(path=".env", kind="secret-likely", risk="high",
                        reason="r", policy_implication="i"),
            RiskSurface(path=".github/workflows", kind="ci", risk="high",
                        reason="r", policy_implication="i"),
            RiskSurface(path="migrations", kind="protected-path", risk="high",
                        reason="r", policy_implication="i"),
        ],
        detected_checks=["pytest", "ruff check ."],
    )


def test_generate_policy_is_conservative():
    p = generate_policy(_scan())
    # protects secrets, CI, migrations
    assert any(".env" in g for g in p.protected_file_globs)
    assert any(".github/workflows" in g for g in p.protected_file_globs)
    assert any("migrations" in g for g in p.protected_file_globs)
    # blocks dangerous shell by default
    assert any("rm -rf" in c for c in p.blocked_shell_commands)
    # deny-by-default MCP allowlist
    assert p.mcp_server_allowlist == []
    # surfaces detected checks as required
    assert "pytest" in p.required_checks
    # gates the risky capability surfaces
    assert {"shell", "credential", "protected-path"} <= set(p.approval_gates)
    assert "Advisory" in p.policy_notes or "advisory" in p.policy_notes


def test_save_and_load_round_trip(tmp_path):
    p = generate_policy(_scan())
    path = tmp_path / "frontier-scout.policy.json"
    save_policy(p, str(path))
    loaded, warnings = load_policy(str(path))
    assert loaded == p and warnings == []


def test_load_missing_file_returns_default_with_warning(tmp_path):
    loaded, warnings = load_policy(str(tmp_path / "nope.json"))
    assert isinstance(loaded, AgentPolicy)
    assert warnings and "not found" in warnings[0].lower()


def test_load_malformed_file_never_crashes(tmp_path):
    bad = tmp_path / "frontier-scout.policy.json"
    bad.write_text("{ this is not json")
    loaded, warnings = load_policy(str(bad))
    assert isinstance(loaded, AgentPolicy)
    assert warnings  # surfaced, not raised


def test_default_policy_path_is_repo_root():
    assert default_policy_path("/x/y").endswith("/x/y/frontier-scout.policy.json")


def test_explain_policy_mentions_advisory_and_gates():
    text = explain_policy(generate_policy(_scan()))
    assert "advisory" in text.lower()
    assert "approval" in text.lower()
