"""P4-1: non-blocking guard notifier + Incident Change Scout parked behind a flag.

TDD (behavior): ``guard --notify`` reports findings but always exits 0 (the soft policy-drift
surface the research wants instead of a hard gate); the ``incident`` module is parked behind
``FRONTIER_SCOUT_EXPERIMENTAL`` during the pivot.
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


def test_incident_parked_behind_experimental_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.delenv("FRONTIER_SCOUT_EXPERIMENTAL", raising=False)
    assert cli.main(["incident", "demo"]) != 0
    assert "experimental" in capsys.readouterr().out.lower()


def test_incident_runs_with_experimental_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_EXPERIMENTAL", "1")
    monkeypatch.setattr(
        cli,
        "run_incident_demo",
        lambda **k: {
            "run_id": "r",
            "answer_path": "a",
            "trace_path": "t",
            "audit_path": "u",
            "eval_path": "e",
            "eval": {"score": 1.0},
            "interrupted": False,
        },
    )
    assert cli.main(["incident", "demo"]) == 0
    assert "experimental" not in capsys.readouterr().out.lower()
