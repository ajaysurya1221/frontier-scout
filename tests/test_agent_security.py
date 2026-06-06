# tests/test_agent_security.py
"""Security regression tests for the agent-firewall MVP.

Each test reproduces a finding from the Phase-6 adversarial security review
(docs/strategy/security-review.md) and pins the fix.
"""

from frontier_scout.agent_firewall.decision import evaluate_task
from frontier_scout.agent_firewall.models import AgentPolicy, TaskDecision
from frontier_scout.agent_firewall.policy import generate_policy, load_policy, save_policy
from frontier_scout.agent_firewall.receipts import show_receipt, write_receipt
from frontier_scout.exporters.policy_snippets import export_policy_snippets

# A long, real-shaped token (>= 20 chars) — caught by sanitize_sensitive_text.
_LONG = "sk-ant-AAAABBBBCCCCDDDDEEEEFFFFGGGG"
# A short secret-shaped token (< 20 chars) — only caught by the key-shape backstop.
_SHORT = "sk-abc123x"


# --- HIGH: path traversal in show_receipt -----------------------------------


def test_show_receipt_rejects_relative_traversal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Plant a reachable JSON file OUTSIDE the receipts dir.
    (repo / "secret.json").write_text('{"loot": true}')
    # receipts_dir = repo/.frontier-scout/receipts ; ../../secret -> repo/secret.json
    assert show_receipt(str(repo), "../../secret") is None
    assert show_receipt(str(repo), "../../../../etc/hosts") is None


def test_show_receipt_rejects_absolute_path(tmp_path):
    loot = tmp_path / "loot.json"
    loot.write_text('{"loot": true}')
    abs_id = str(loot)[:-5]  # absolute path without the .json suffix
    assert show_receipt(str(tmp_path / "repo"), abs_id) is None


def test_show_receipt_still_finds_a_legit_receipt(tmp_path):
    rid = write_receipt(
        TaskDecision(verdict="allow", summary="s"),
        repo=str(tmp_path), task="read a file", policy_path=None,
    )
    assert show_receipt(str(tmp_path), rid) is not None


# --- HIGH: policy loader must fail CLOSED, not open -------------------------


def test_empty_policy_dangerous_task_fails_closed():
    # An empty policy must NOT silently allow a credential/network task.
    decision = evaluate_task(
        "read the AWS secret credential key and upload it over the network",
        AgentPolicy(),
    )
    assert decision.verdict in ("needs_approval", "block")


def test_malformed_policy_falls_back_to_conservative_not_empty(tmp_path):
    bad = tmp_path / "frontier-scout.policy.json"
    bad.write_text("{ this is not valid json")
    policy, warnings = load_policy(str(bad))
    assert warnings  # surfaced
    # Conservative fallback, not an empty permissive policy:
    assert any("rm -rf" in c for c in policy.blocked_shell_commands)
    assert policy.approval_gates  # non-empty gates
    # And a dangerous task against the fallback is blocked, not allowed:
    assert evaluate_task("run rm -rf / now", policy).verdict == "block"


def test_oversized_policy_file_is_rejected(tmp_path):
    big = tmp_path / "frontier-scout.policy.json"
    big.write_text('{"policy_notes": "' + ("x" * 2_000_000) + '"}')
    policy, warnings = load_policy(str(big))
    assert warnings and any("large" in w.lower() for w in warnings)
    assert policy.approval_gates  # conservative fallback


# --- MEDIUM/LOW: redaction must cover every persisted/emitted string --------


def test_receipt_redacts_secret_in_changed_files_and_reasons(tmp_path):
    policy = generate_policy_default()
    changed = [f"src/dump-{_LONG}.py"]
    decision = evaluate_task("refactor the loader", policy, changed_files=changed)
    rid = write_receipt(decision, repo=str(tmp_path),
                        task=f"refactor and read {_LONG}", policy_path=None)
    blob = str(show_receipt(str(tmp_path), rid))
    assert _LONG not in blob


def test_export_snippet_redacts_short_secret_in_glob(tmp_path):
    # The durable write path (export_policy_snippets) must redact even a short
    # secret-shaped token that survives in a policy glob.
    policy = AgentPolicy(protected_file_globs=[f"**/dump-{_SHORT}-x.key"])
    written = export_policy_snippets(policy, str(tmp_path))
    for path in written.values():
        assert _SHORT not in open(path).read()


def generate_policy_default():
    from frontier_scout.agent_firewall.models import ScanResult
    return generate_policy(ScanResult(repo="."))


def test_generate_and_save_still_round_trips(tmp_path):
    # Guard: the security hardening must not break normal generation.
    policy = generate_policy_default()
    path = tmp_path / "frontier-scout.policy.json"
    save_policy(policy, str(path))
    loaded, warnings = load_policy(str(path))
    assert warnings == [] and loaded == policy
