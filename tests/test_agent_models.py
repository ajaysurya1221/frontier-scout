from frontier_scout.agent_firewall.models import (
    AgentPolicy,
    Receipt,
    RiskSurface,
    ScanResult,
    TaskDecision,
)


def test_agent_policy_defaults_are_empty_and_versioned():
    p = AgentPolicy()
    assert p.version == 1
    for field in (
        "allowed_tools", "blocked_tools", "allowed_shell_commands",
        "blocked_shell_commands", "allowed_file_globs", "protected_file_globs",
        "mcp_server_allowlist", "required_checks", "approval_gates",
    ):
        assert getattr(p, field) == []
    assert p.policy_notes == ""


def test_agent_policy_round_trips_through_json():
    p = AgentPolicy(blocked_shell_commands=["rm -rf"], approval_gates=["shell"])
    again = AgentPolicy.model_validate(p.model_dump())
    assert again == p


def test_models_carry_static_only_honesty_markers():
    assert ScanResult(repo=".").static_only is True
    assert TaskDecision(verdict="allow", summary="ok").static_only is True
    assert Receipt(
        receipt_id="x", timestamp="t", repo=".", task_summary="s", verdict="allow"
    ).kind == "static-policy-assessment"


def test_risk_surface_requires_core_fields():
    s = RiskSurface(path=".env", kind="secret-likely", risk="high",
                    reason="r", policy_implication="i")
    assert s.suggested_checks == []
    assert s.risk == "high"
