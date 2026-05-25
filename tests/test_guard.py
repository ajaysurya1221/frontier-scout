import json

from frontier_scout.evaluate import evaluate_url
from frontier_scout.guard import format_findings, run_guard
from frontier_scout.mcp_audit import PermissionManifest
from frontier_scout.store import init_db, save_evaluation, save_permission_manifest


def test_guard_reports_missing_trial_for_dangerous_capability(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()
    evaluation = evaluate_url("https://github.com/modelcontextprotocol/servers")
    tool_id = save_evaluation(evaluation)
    save_permission_manifest(
        tool_id,
        PermissionManifest(
            tool_name=evaluation.tool_name,
            source_url=evaluation.source_url,
            capabilities={"read": "likely", "write": "likely"},
            dangerous_flags=["write"],
            evidence_source="fixture",
            confidence="medium",
        ),
    )

    findings = run_guard(tmp_path)

    assert any(f.rule_id == "trial.required" for f in findings)
    assert "Frontier Scout Guard: failed" in format_findings(findings)


def test_guard_json_format_is_machine_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()
    rendered = format_findings([], output_format="json")

    payload = json.loads(rendered)
    assert payload == {"status": "passed", "findings": []}


def test_guard_github_format_uses_annotations():
    rendered = format_findings(
        [
            {
                "severity": "high",
                "rule_id": "trial.required",
                "message": "Trial required",
                "tool_name": "x/y",
            }
        ],
        output_format="github",
    )

    assert "::warning title=trial.required::x/y: Trial required" in rendered
