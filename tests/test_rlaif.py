"""Stream 3 — RLAIF harness plumbing (offline, zero spend).

Covers the budget accounting, the dry-run cycle, and the report writer
without touching a live LLM. The live reinforcement loop itself is exercised
manually with real keys (see demo/rlaif-report.md); these tests pin the
safety-critical scaffolding: cumulative spend is read honestly from the
ledger, the cap halts the loop, and the report renders findings.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture
def rlaif(monkeypatch, tmp_path):
    """Import rlaif with a fresh session + isolated ledger/report paths."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(home))
    monkeypatch.setenv("RLAIF_SESSION", "rlaif-test-abc123")
    # Reimport cost_tracker so LEDGER points at the temp home, then rlaif.
    import cost_tracker

    importlib.reload(cost_tracker)
    import rlaif as rlaif_mod

    importlib.reload(rlaif_mod)
    # Redirect the report into tmp so we never clobber the real artifact.
    rlaif_mod._REPORT_PATH = tmp_path / "rlaif-report.md"
    return rlaif_mod


def _append_ledger(home: Path, run_id: str, cost: float) -> None:
    ledger = home / "costs.jsonl"
    with ledger.open("a") as fh:
        fh.write(json.dumps({"run_id": run_id, "cost_usd": cost}) + "\n")


def test_session_spend_sums_only_this_session(rlaif, tmp_path):
    home = tmp_path / "home"
    _append_ledger(home, "rlaif-test-abc123", 1.25)
    _append_ledger(home, "rlaif-test-abc123", 0.75)
    _append_ledger(home, "some-other-run", 9.99)
    assert rlaif._session_spend() == pytest.approx(2.0)


def test_session_spend_zero_when_no_ledger(rlaif):
    assert rlaif._session_spend() == 0.0


def test_dry_run_cycle_is_clean_and_free(rlaif):
    record = rlaif.run_cycle(1, dry_run=True)
    assert record["clean"] is True
    assert record["scan_cost_usd"] == 0.0
    assert record["audit_cost_usd"] == 0.0
    assert record["verdicts"]  # fixture verdicts present


def test_report_renders_findings(rlaif):
    cycle = {
        "cycle": 1,
        "started": "2026-05-29T00:00:00+00:00",
        "verdicts": [{"tool_name": "FastAPI", "verdict": "assess", "category": "dev_tool", "what": "web framework"}],
        "scan_cost_usd": 0.4,
        "audit_cost_usd": 0.1,
        "audit": {
            "overall_rating": "needs_work",
            "summary": "One framework leaked.",
            "rubric_recommendation": "Add FastAPI to the infra backstop.",
        },
        "scope_false_positives": [
            {"tool_name": "FastAPI", "scope_reason": "generic web framework, no AI surface"}
        ],
        "quality_issues": [],
        "clean": False,
    }
    path = rlaif.write_report([cycle], cap=60.0, spend=0.5, satisfied=False)
    text = path.read_text()
    assert "RLAIF Report" in text
    assert "FastAPI" in text
    assert "Scope false-positives: 1" in text
    assert "needs_work" in text
    assert "in progress" in text


def test_main_dry_run_stops_after_two_clean(rlaif, capsys):
    rc = rlaif.main(["--dry-run", "--cycles", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RLAIF loop satisfied" in out
    # Stopped at 2 consecutive clean — never reached cycle 3.
    assert "RLAIF cycle 3" not in out


def test_main_dry_run_respects_cap(rlaif, tmp_path, capsys):
    home = tmp_path / "home"
    _append_ledger(home, "rlaif-test-abc123", 100.0)  # already over a $60 cap
    rc = rlaif.main(["--dry-run", "--cycles", "3", "--cap", "60"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Budget cap reached" in out
