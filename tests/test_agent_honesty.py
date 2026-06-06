# tests/test_agent_honesty.py
"""Copy/behaviour guards for the agent-firewall MVP honesty invariants.

These assert the product stays *static and advisory*: it never claims runtime
enforcement, compliance, or that a task ran, and every artifact carries the
``static_only`` marker.
"""

from frontier_scout.agent_firewall.decision import evaluate_task
from frontier_scout.agent_firewall.models import ScanResult
from frontier_scout.agent_firewall.policy import explain_policy, generate_policy
from frontier_scout.agent_firewall.scan import scan_repo
from frontier_scout.exporters.policy_snippets import (
    build_agents_md_snippet,
    build_claude_md_snippet,
    build_pr_checklist,
)

# Overclaim phrases that must never appear in user-facing agent-firewall output.
_FORBIDDEN = (
    "signed-by",
    "witnessed",
    "guarantees complete",
    "enterprise-grade",
    "soc2",
    "fully secure",
    "complete protection",
)


def test_scan_and_policy_copy_is_advisory_not_enforcing(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# x\n")
    (tmp_path / ".env").write_text("X=1\n")
    scan = scan_repo(str(tmp_path))
    policy = generate_policy(scan)
    text = (explain_policy(policy) + scan.model_dump_json()).lower()
    for bad in _FORBIDDEN:
        assert bad not in text, f"overclaim phrase leaked: {bad!r}"
    assert scan.static_only is True


def test_explain_policy_states_it_is_advisory():
    policy = generate_policy(ScanResult(repo="."))
    assert "advisory" in explain_policy(policy).lower()


def test_export_snippets_say_they_do_not_enforce():
    policy = generate_policy(ScanResult(repo=".", detected_checks=["pytest"]))
    for builder in (build_claude_md_snippet, build_agents_md_snippet, build_pr_checklist):
        text = builder(policy).lower()
        assert "advisory" in text
        assert "does not enforce" in text or "not enforced" in text
        for bad in _FORBIDDEN:
            assert bad not in text


def test_decision_is_static_only_and_block_is_advisory():
    decision = evaluate_task("run rm -rf / now", generate_policy(ScanResult(repo=".")))
    assert decision.static_only is True
    assert decision.verdict == "block"
    # The summary must not imply the task executed or was enforced.
    summary = decision.summary.lower()
    assert "executed" not in summary
    for bad in _FORBIDDEN:
        assert bad not in summary
