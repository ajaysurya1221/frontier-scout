"""Policy-loading + repo scoping (Codex review finding #2).

Until v1.2.1, ``evaluate_policy(...)`` was called everywhere without a
``policy=`` argument, so the repo's ``.frontier-scout/policy.toml`` was
silently ignored. These tests cover the wired paths.
"""

from __future__ import annotations

from pathlib import Path

from frontier_scout.evaluate import Evaluation
from frontier_scout.mcp_audit import PermissionManifest
from frontier_scout.policy import (
    DEFAULT_POLICY,
    Policy,
    evaluate_policy,
    load_policy,
)


def _policy_toml(allow_low_risk_no_lab: bool = True) -> str:
    return (
        "[policy]\n"
        f"allow_adopt_without_lab_for_low_risk = {str(allow_low_risk_no_lab).lower()}\n"
        "require_trial_for_dangerous_capabilities = true\n"
        "fail_unknown_capabilities = true\n"
        "strict = false\n"
    )


def _clean_evaluation() -> Evaluation:
    return Evaluation(
        tool_name="example/clean-tool",
        source_url="https://github.com/example/clean-tool",
        category="dev_tool",
        fit="high",
        risk="low",
        source_trust="high",
        score=9,
        permission_manifest=PermissionManifest(
            tool_name="example/clean-tool",
            source_url="https://github.com/example/clean-tool",
            evidence_source="url",
            confidence="high",
            capabilities={},
            dangerous_flags=[],
        ),
    )


# ---------------------------------------------------------------------------
# load_policy cascade
# ---------------------------------------------------------------------------


def test_load_policy_uses_repo_file_when_present(tmp_path):
    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    (fs_dir / "policy.toml").write_text(_policy_toml(allow_low_risk_no_lab=True))

    policy = load_policy(tmp_path)
    assert isinstance(policy, Policy)
    assert policy.allow_adopt_without_lab_for_low_risk is True


def test_load_policy_falls_back_to_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".frontier-scout"
    home.mkdir(parents=True)
    (home / "policy.toml").write_text(_policy_toml(allow_low_risk_no_lab=False))
    monkeypatch.setattr(Path, "expanduser", lambda p: home / "policy.toml")

    policy = load_policy(tmp_path)
    assert policy.allow_adopt_without_lab_for_low_risk is False


def test_load_policy_default_when_nothing_set(tmp_path):
    policy = load_policy(tmp_path)
    assert policy is DEFAULT_POLICY or policy.model_dump() == DEFAULT_POLICY.model_dump()


# ---------------------------------------------------------------------------
# Custom policy actually changes evaluate_policy decisions
# ---------------------------------------------------------------------------


def test_custom_policy_allows_adopt_without_lab():
    """allow_adopt_without_lab_for_low_risk=True → clean high-fit/low-risk
    evaluation gets ADOPT without a stored lab receipt."""

    evaluation = _clean_evaluation()
    permissive = Policy(allow_adopt_without_lab_for_low_risk=True)
    decision = evaluate_policy(evaluation, evaluation.permission_manifest, policy=permissive)
    assert decision.verdict == "adopt"


def test_default_policy_forces_assess_or_trial_without_lab():
    """allow_adopt_without_lab_for_low_risk defaults to False → same clean
    evaluation without lab evidence stays in ASSESS."""

    evaluation = _clean_evaluation()
    decision = evaluate_policy(
        evaluation,
        evaluation.permission_manifest,
        policy=DEFAULT_POLICY,
    )
    assert decision.verdict in {"assess", "trial"}


# ---------------------------------------------------------------------------
# CLI evaluate now passes policy through (Codex #2 wiring)
# ---------------------------------------------------------------------------


def test_cli_evaluate_loads_repo_policy(tmp_path, monkeypatch, capsys):
    """When ``frontier-scout evaluate <url> --repo PATH`` runs and PATH
    contains a custom policy, the JSON output reflects the custom policy
    decision."""

    # CodeRabbit (PR #18): the CLI run itself must prove the repo policy was
    # consulted. We pick a lever whose effect is observable in the CLI's own
    # JSON for the URL the CLI actually evaluates. The evaluated tool carries a
    # ``network`` capability flag, so under the DEFAULT policy
    # (``require_trial_for_dangerous_capabilities = true``) it produces a
    # ``capability.network`` finding and a TRIAL verdict. The repo policy below
    # sets that flag to ``false`` — which the engine honours by dropping the
    # finding and downgrading the verdict to ASSESS. If the CLI ignored the repo
    # file (regressed to DEFAULT_POLICY), this run would say "trial" and the
    # assertion would fail.
    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    (fs_dir / "policy.toml").write_text(
        "[policy]\n"
        "require_trial_for_dangerous_capabilities = false\n"
        "fail_unknown_capabilities = false\n"
    )
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))

    from frontier_scout.cli import main

    rc = main([
        "evaluate",
        "https://github.com/anthropics/skills",
        "--repo", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    import json

    payload = json.loads(capsys.readouterr().out)

    # Sanity: confirm DEFAULT_POLICY would have said "trial" for these inputs —
    # so "assess" below can only come from the repo file being loaded.
    from frontier_scout.evaluate import evaluate_url
    from frontier_scout.mcp_audit import classify_mcp_capabilities
    from frontier_scout.policy import DEFAULT_POLICY, evaluate_policy, load_policy
    from frontier_scout.scout import detect_stack

    _ev = evaluate_url("https://github.com/anthropics/skills", detect_stack(tmp_path))
    _manifest = _ev.permission_manifest or classify_mcp_capabilities(
        "https://github.com/anthropics/skills", tool_name=_ev.tool_name
    )
    default_verdict = evaluate_policy(_ev, _manifest, policy=DEFAULT_POLICY).verdict
    assert default_verdict == "trial"

    # The CLI run, with the repo policy loaded, MUST diverge from the default.
    assert payload["policy"]["verdict"] == "assess"
    assert payload["policy"]["verdict"] != default_verdict

    # And the loaded policy really is the repo file (not DEFAULT_POLICY).
    loaded = load_policy(tmp_path)
    assert loaded.require_trial_for_dangerous_capabilities is False
    assert loaded is not DEFAULT_POLICY


# ---------------------------------------------------------------------------
# Guard honours strict
# ---------------------------------------------------------------------------


def test_run_guard_strict_upgrades_medium_to_high(tmp_path, monkeypatch):
    """Codex review noted ``strict`` was silently ignored. v1.2.1 honours
    it: every medium-severity finding becomes high so CI treats them as
    failing."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))

    from frontier_scout import guard

    fake_records = [
        {
            "tool_name": "tool-a",
            "dangerous_flags": ["network"],  # base severity = medium
            "latest_trial_status": None,
            "latest_decision": None,
        }
    ]
    monkeypatch.setattr(guard, "list_guard_records", lambda: fake_records)

    lax = guard.run_guard(strict=False)
    strict = guard.run_guard(strict=True)
    assert lax[0].severity == "medium"
    assert strict[0].severity == "high"


# ---------------------------------------------------------------------------
# Stream H — Policy.require_trial_for_dangerous_capabilities actually fires
# ---------------------------------------------------------------------------


def _network_evaluation() -> Evaluation:
    """Clean high-fit/low-risk tool that exposes a network capability."""

    return Evaluation(
        tool_name="example/network-tool",
        source_url="https://github.com/example/network-tool",
        category="dev_tool",
        fit="high",
        risk="low",
        source_trust="high",
        score=9,
        permission_manifest=PermissionManifest(
            tool_name="example/network-tool",
            source_url="https://github.com/example/network-tool",
            evidence_source="url",
            confidence="high",
            capabilities={"network": "likely"},
            dangerous_flags=["network"],
        ),
    )


def test_require_trial_flag_off_skips_capability_findings():
    """Stream H: when an operator sets
    ``require_trial_for_dangerous_capabilities = false`` (e.g. internal
    toolchain where every tool *is* network-capable by design), the
    capability.* findings disappear and a clean high-fit / low-risk
    evaluation can ADOPT without a stored lab receipt."""

    evaluation = _network_evaluation()
    permissive = Policy(
        require_trial_for_dangerous_capabilities=False,
        allow_adopt_without_lab_for_low_risk=True,
    )
    decision = evaluate_policy(
        evaluation, evaluation.permission_manifest, policy=permissive
    )
    rule_ids = {f.rule_id for f in decision.findings}
    assert "capability.network" not in rule_ids
    assert decision.verdict == "adopt"


def test_require_trial_flag_on_still_emits_capability_findings():
    """Default policy: the flag is True; network capability *does*
    surface a finding and the verdict is TRIAL, not ADOPT."""

    evaluation = _network_evaluation()
    decision = evaluate_policy(
        evaluation, evaluation.permission_manifest, policy=DEFAULT_POLICY
    )
    rule_ids = {f.rule_id for f in decision.findings}
    assert "capability.network" in rule_ids
    assert decision.verdict == "trial"


def test_require_trial_flag_off_does_not_silence_unknown():
    """Critical: setting the gate flag to False must NOT suppress the
    capability.unknown branch — unknowns are correctness, not
    preference. The flag only relaxes the *known* dangerous flags."""

    evaluation = Evaluation(
        tool_name="example/mystery",
        source_url="https://github.com/example/mystery",
        category="dev_tool",
        fit="medium",
        risk="medium",
        source_trust="medium",
        score=6,
        permission_manifest=PermissionManifest(
            tool_name="example/mystery",
            source_url="https://github.com/example/mystery",
            evidence_source="url",
            confidence="low",
            capabilities={"unknown": "likely"},
            dangerous_flags=["unknown"],
        ),
    )
    permissive = Policy(
        require_trial_for_dangerous_capabilities=False,
        fail_unknown_capabilities=True,  # default
    )
    decision = evaluate_policy(
        evaluation, evaluation.permission_manifest, policy=permissive
    )
    rule_ids = {f.rule_id for f in decision.findings}
    assert "capability.unknown" in rule_ids
    assert decision.verdict == "hold"
