"""P4-1: non-blocking guard notifier.

TDD (behavior): ``guard --notify`` reports findings but always exits 0 (the soft policy-drift
surface the research wants instead of a hard gate).
"""

from frontier_scout import cli
from frontier_scout.policy import PolicyFinding


def test_guard_notify_is_non_blocking_with_high_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    high = [PolicyFinding(severity="high", rule_id="trial.required", message="m", tool_name="t")]
    monkeypatch.setattr(cli, "run_guard", lambda *a, **k: high)
    # default guard is blocking: a high finding -> exit 1
    assert cli.main(["guard", "--repo", str(tmp_path)]) == 1
    # --notify is non-blocking: same finding -> exit 0
    assert cli.main(["guard", "--repo", str(tmp_path), "--notify"]) == 0
