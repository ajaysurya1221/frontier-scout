# tests/test_agent_receipts.py
from frontier_scout.agent_firewall.models import TaskDecision
from frontier_scout.agent_firewall.receipts import (
    list_receipts,
    receipts_dir,
    show_receipt,
    write_receipt,
)


def _decision():
    return TaskDecision(verdict="needs_approval", summary="s",
                        required_checks=["pytest"], files_considered=["a.py"])


def test_write_then_list_and_show(tmp_path):
    repo = str(tmp_path)
    rid = write_receipt(_decision(), repo=repo,
                        task="read the AWS secret sk-ant-PLANTED and edit a.py",
                        policy_path="frontier-scout.policy.json")
    assert receipts_dir(repo).exists()
    listed = list_receipts(repo)
    assert len(listed) == 1 and listed[0]["receipt_id"] == rid
    one = show_receipt(repo, rid)
    assert one is not None and one["verdict"] == "needs_approval"
    assert one["kind"] == "static-policy-assessment"
    for field in ("receipt_id", "timestamp", "repo", "task_summary",
                  "verdict", "reasons", "files_considered", "required_checks",
                  "frontier_scout_version"):
        assert field in one


def test_receipt_redacts_secrets_in_task_summary(tmp_path):
    repo = str(tmp_path)
    rid = write_receipt(_decision(), repo=repo,
                        task="use sk-ant-PLANTEDSECRETVALUE now", policy_path=None)
    one = show_receipt(repo, rid)
    assert "sk-ant-PLANTEDSECRETVALUE" not in one["task_summary"]


def test_list_tolerates_corrupt_file(tmp_path):
    repo = str(tmp_path)
    write_receipt(_decision(), repo=repo, task="t", policy_path=None)
    (receipts_dir(repo) / "broken.json").write_text("{ not json")
    listed = list_receipts(repo)  # must not raise
    assert isinstance(listed, list)


def test_show_missing_receipt_returns_none(tmp_path):
    assert show_receipt(str(tmp_path), "does-not-exist") is None
