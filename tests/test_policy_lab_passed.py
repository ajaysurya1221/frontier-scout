"""Regression test for the lab_passed operator-precedence bug (RLAIF cycle 6).

policy._decide previously derived:
    lab_passed = status=='passed' OR exit_code==0 AND status in {passed,completed}
Because `and` binds tighter than `or`, a lab_result with status='completed' but
NO 'exit_code' key evaluated the exit_code==0 term as False, so a genuinely
finished clean trial was treated as not-passed — silently downgrading an
otherwise-adoptable tool from ADOPT to ASSESS.

The fix treats a 'completed' status with a 0-or-absent exit_code as passed,
while preserving "status=='passed' always passes" and "completed + nonzero
exit_code fails".
"""

from __future__ import annotations

import pytest

from frontier_scout.evaluate import Evaluation
from frontier_scout.mcp_audit import PermissionManifest
from frontier_scout.policy import DEFAULT_POLICY, evaluate_policy


def _evaluation() -> Evaluation:
    # High-fit, LOW-risk, trusted source with a clean read-only manifest → no
    # findings, so the verdict is driven purely by the lab_result and the adopt
    # path (which requires risk=="low") is reachable. That is exactly where the
    # lab_passed precedence bug bit: a finished clean trial should ADOPT, and a
    # missing exit_code key must not silently knock it down to ASSESS.
    return Evaluation(
        tool_name="demo/tool",
        source_url="https://github.com/demo/tool",
        category="dev_tool",
        fit="high",
        risk="low",
        source_trust="high",
    )


def _manifest() -> PermissionManifest:
    return PermissionManifest(
        tool_name="demo/tool",
        capabilities={"read": "likely"},
        dangerous_flags=[],
        confidence="high",
    )


def _verdict(lab):
    return evaluate_policy(_evaluation(), _manifest(), lab, policy=DEFAULT_POLICY).verdict


@pytest.mark.parametrize(
    "lab,expected",
    [
        ({"status": "completed", "exit_code": 0}, "adopt"),
        # The bug: same finished trial, exit_code key omitted.
        ({"status": "completed"}, "adopt"),
        ({"status": "passed"}, "adopt"),
        ({"status": "passed", "exit_code": 0}, "adopt"),
    ],
)
def test_finished_clean_trial_adopts(lab, expected):
    assert _verdict(lab) == expected


def test_completed_with_nonzero_exit_does_not_adopt():
    # A completed-but-failing trial must NOT be treated as passed.
    assert _verdict({"status": "completed", "exit_code": 1}) != "adopt"


def test_completed_without_exitcode_matches_exit0():
    # The core regression: presence/absence of exit_code must not change a
    # finished clean trial's verdict.
    assert _verdict({"status": "completed"}) == _verdict(
        {"status": "completed", "exit_code": 0}
    )
