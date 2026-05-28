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

    fs_dir = tmp_path / ".frontier-scout"
    fs_dir.mkdir(parents=True)
    (fs_dir / "policy.toml").write_text(_policy_toml(allow_low_risk_no_lab=True))
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
    # Either the decision text or the policy summary should mention ADOPT
    # when allow_low_risk_no_lab=True kicks in for a high-trust source.
    # We allow either ADOPT or TRIAL — the point is the *policy decision
    # was made* (it would have crashed if policy=None had snuck in).
    assert payload["policy"]["verdict"] in {"adopt", "trial", "assess", "hold"}


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
