from pathlib import Path

from frontier_scout.evaluate import evaluate_url
from frontier_scout.mcp_audit import classify_mcp_capabilities
from frontier_scout.store import (
    create_trial_run,
    db_path,
    finish_trial_run,
    init_db,
    latest_trial_for_tool,
    save_evaluation,
    save_lab_result,
    save_permission_manifest,
)
from frontier_scout.trials import render_trial_receipt, run_trial


def test_store_persists_evaluation_manifest_and_trial(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    init_db()

    evaluation = evaluate_url("https://github.com/browser-use/browser-use")
    manifest = classify_mcp_capabilities("browser automation over public pages")
    tool_id = save_evaluation(evaluation)
    save_permission_manifest(tool_id, manifest)
    trial_id = create_trial_run(tool_id, requested_action="dry-run")
    save_lab_result(
        trial_id,
        {
            "runtime": "python",
            "status": "skipped",
            "exit_code": 0,
            "duration_s": 0,
            "cost_usd": 0,
        },
    )
    finish_trial_run(trial_id, status="completed", decision="trial")

    latest = latest_trial_for_tool("browser-use/browser-use")

    assert db_path().exists()
    assert latest is not None
    assert latest["decision"] == "trial"
    assert latest["lab_result"]["status"] == "skipped"


def test_run_trial_dry_run_writes_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))

    result = run_trial(
        "browser-use/browser-use",
        url="https://github.com/browser-use/browser-use",
        dry_run=True,
    )

    receipt_path = Path(result["receipt_path"])
    assert receipt_path.exists()
    assert "TRIAL receipt: browser-use/browser-use" in receipt_path.read_text()


def test_render_trial_receipt_includes_policy_and_permissions():
    receipt = render_trial_receipt(
        tool_name="x/y",
        source_url="https://github.com/x/y",
        decision="trial",
        policy_summary="TRIAL - write capability requires sandbox evidence.",
        capabilities={"read": "likely", "write": "likely"},
        lab_result={"status": "skipped", "runtime": "python"},
    )

    assert "Permission manifest" in receipt
    assert "write: likely" in receipt
    assert "Lab result" in receipt
