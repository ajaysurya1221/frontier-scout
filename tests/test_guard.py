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


def test_guard_fails_closed_on_missing_manifest(tmp_path, monkeypatch):
    # A tool with NO stored permission manifest must NOT silently pass: the
    # pre-fix INNER JOIN dropped these rows entirely (fail open). Guard now
    # surfaces a high ``capability.missing`` finding, matching evaluate_policy.
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()
    save_evaluation(evaluate_url("https://github.com/no-manifest/tool"))

    findings = run_guard(tmp_path)

    rules = {(f.rule_id, f.severity, f.tool_name) for f in findings}
    assert any(
        rule == "capability.missing" and sev == "high" for (rule, sev, _t) in rules
    ), rules
    assert "Frontier Scout Guard: failed" in format_findings(findings)


def test_guard_missing_manifest_is_high_even_in_lax_mode(tmp_path, monkeypatch):
    # capability.missing is blocking regardless of ``strict`` (already high;
    # strict only upgrades medium → high).
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()
    save_evaluation(evaluate_url("https://github.com/no-manifest/tool"))

    lax = run_guard(tmp_path, strict=False)
    assert any(f.rule_id == "capability.missing" and f.severity == "high" for f in lax)


def test_guard_uses_latest_manifest_and_mixes_with_missing(tmp_path, monkeypatch):
    # Two manifests on one tool → use the LATEST (dangerous); a clean tool with
    # a manifest produces nothing; a manifest-less tool fails closed.
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()

    evolving = save_evaluation(evaluate_url("https://github.com/evolving/tool"))
    save_permission_manifest(
        evolving, PermissionManifest(tool_name="evolving/tool", dangerous_flags=[])
    )
    save_permission_manifest(
        evolving, PermissionManifest(tool_name="evolving/tool", dangerous_flags=["shell"])
    )

    clean = save_evaluation(evaluate_url("https://github.com/clean/tool"))
    save_permission_manifest(
        clean, PermissionManifest(tool_name="clean/tool", dangerous_flags=[])
    )

    save_evaluation(evaluate_url("https://github.com/ghost/tool"))  # no manifest

    findings = run_guard(tmp_path)
    by_tool = {f.tool_name: f.rule_id for f in findings}

    # Latest manifest (shell) → guard's trial.required rule fires.
    assert by_tool.get("evolving/tool") == "trial.required"
    # Manifest-less tool fails closed.
    assert by_tool.get("ghost/tool") == "capability.missing"
    # Clean tool with a manifest produces no finding.
    assert "clean/tool" not in by_tool
