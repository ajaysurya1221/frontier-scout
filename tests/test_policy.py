from frontier_scout.evaluate import Evaluation
from frontier_scout.mcp_audit import PermissionManifest
from frontier_scout.policy import evaluate_policy


def test_policy_holds_unknown_capability_surface():
    evaluation = Evaluation(
        tool_name="example/agent",
        source_url="https://github.com/example/agent",
        category="agent_framework",
        fit="medium",
        risk="medium",
        source_trust="medium",
        evidence=["GitHub repository"],
    )
    manifest = PermissionManifest(
        tool_name="example/agent",
        source_url="https://github.com/example/agent",
        capabilities={"unknown": "likely"},
        dangerous_flags=["unknown"],
        evidence_source="empty",
        confidence="low",
    )

    decision = evaluate_policy(evaluation, manifest)

    assert decision.verdict == "hold"
    assert any(f.rule_id == "capability.unknown" for f in decision.findings)


def test_policy_trials_write_capabilities_without_lab_result():
    evaluation = Evaluation(
        tool_name="modelcontextprotocol/filesystem",
        source_url="https://github.com/modelcontextprotocol/servers",
        category="mcp_server",
        fit="high",
        risk="medium",
        source_trust="high",
        evidence=["MCP server source"],
    )
    manifest = PermissionManifest(
        tool_name="modelcontextprotocol/filesystem",
        source_url="https://github.com/modelcontextprotocol/servers",
        capabilities={"read": "likely", "write": "likely"},
        dangerous_flags=["write"],
        evidence_source="README",
        confidence="medium",
    )

    decision = evaluate_policy(evaluation, manifest)

    assert decision.verdict == "trial"
    assert any(f.severity == "high" for f in decision.findings)


def test_policy_adopts_high_fit_low_risk_with_clean_lab_result():
    evaluation = Evaluation(
        tool_name="anthropics/skills",
        source_url="https://github.com/anthropics/skills",
        category="skill",
        fit="high",
        risk="low",
        source_trust="high",
        evidence=["Major-lab maintained repo"],
    )
    manifest = PermissionManifest(
        tool_name="anthropics/skills",
        source_url="https://github.com/anthropics/skills",
        capabilities={"read": "likely", "write": "unlikely"},
        dangerous_flags=[],
        evidence_source="README",
        confidence="high",
    )
    lab_result = {"status": "passed", "exit_code": 0}

    decision = evaluate_policy(evaluation, manifest, lab_result)

    assert decision.verdict == "adopt"
    assert decision.findings == []
