from pathlib import Path

from frontier_scout.platform.incident_change_scout.workflow import run_incident_demo


def test_incident_demo_runs_end_to_end_with_interrupt(tmp_path):
    summary = run_incident_demo(
        corpus_dir=Path("examples/incident_change_scout/corpus"),
        ticket_path=Path("examples/incident_change_scout/tickets/cache-storm.md"),
        output_dir=tmp_path,
    )

    assert summary["interrupted"] is True
    assert Path(summary["answer_path"]).exists()
    assert Path(summary["trace_path"]).read_text()
    assert Path(summary["audit_path"]).read_text()
    assert summary["eval"]["passed"] is True

