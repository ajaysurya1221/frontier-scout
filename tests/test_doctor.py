"""Tests for the doctor agent-readiness checks."""

from __future__ import annotations

import json

from frontier_scout.agent_firewall.compile import compile_claude
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.doctor import render_json, render_text, run_doctor


def test_doctor_flags_uncompiled_repo(tmp_path):
    checks = run_doctor(str(tmp_path))
    names = {c.name for c in checks}
    assert {"policy", "lock", "settings", "hooks"} <= names
    # An empty repo is not compiled — policy/lock/settings/hooks should fail.
    by_name = {c.name: c for c in checks}
    assert by_name["lock"].status == "fail"
    assert by_name["hooks"].status == "fail"


def test_doctor_passes_after_compile(tmp_path):
    compile_claude(AgentPolicy(allowed_file_globs=["src/**"]), repo=str(tmp_path))
    checks = run_doctor(str(tmp_path))
    by_name = {c.name: c for c in checks}
    assert by_name["lock"].status == "pass"
    assert by_name["settings"].status == "pass"
    assert by_name["hooks"].status == "pass"
    assert by_name["policy-lock-match"].status == "pass"


def test_doctor_detects_policy_drift(tmp_path):
    compile_claude(AgentPolicy(allowed_file_globs=["src/**"]), repo=str(tmp_path))
    (tmp_path / "frontier-scout.policy.json").write_text('{"version": 1, "allowed_tools": ["X"]}')
    by_name = {c.name: c for c in run_doctor(str(tmp_path))}
    assert by_name["policy-lock-match"].status == "fail"


def test_doctor_text_and_json_render(tmp_path):
    checks = run_doctor(str(tmp_path))
    assert "policy:" in render_text(checks)
    payload = json.loads(render_json(checks))
    assert isinstance(payload, list) and payload[0]["name"] == "policy"
