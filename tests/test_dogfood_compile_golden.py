# tests/test_dogfood_compile_golden.py
"""Source-of-truth golden test for the repo's committed dogfood compile artifacts.

A fresh compile of the committed `frontier-scout.policy.json` must reproduce the
committed `.claude/` controls byte-for-byte (volatile lock fields normalized). This
makes it impossible for `.claude/hooks/_fs_guard.py` to drift unnoticed from the
source `hook_runtime.py`, or for the generated verify workflow to lose its
least-privilege hardening. Compilation runs into a temp dir — never over the tree.
"""
import json
from pathlib import Path

from frontier_scout.agent_firewall import hook_runtime
from frontier_scout.agent_firewall.compile import _WORKFLOW, compile_claude
from frontier_scout.agent_firewall.lock import policy_hash
from frontier_scout.agent_firewall.policy import load_policy

REPO = Path(__file__).resolve().parent.parent

# Artifacts the compiler fully owns and produces deterministically: a fresh compile
# must match the committed copy byte-for-byte.
_BYTE_IDENTICAL = [
    "frontier-scout.policy.json",
    ".claude/settings.json",
    ".claude/hooks/_fs_guard.py",
    ".claude/hooks/pre_tool_use.py",
    ".claude/hooks/post_tool_use.py",
]


def _compile_committed_policy_into(tmp_path: Path) -> None:
    policy, warnings = load_policy(str(REPO / "frontier-scout.policy.json"))
    assert warnings == [], f"committed policy did not load clean: {warnings}"
    compile_claude(policy, repo=str(tmp_path), out_dir=str(tmp_path))


def test_committed_dogfood_artifacts_match_fresh_compile(tmp_path):
    _compile_committed_policy_into(tmp_path)
    for rel in _BYTE_IDENTICAL:
        committed = (REPO / rel).read_text()
        fresh = (tmp_path / rel).read_text()
        assert fresh == committed, (
            f"{rel} has drifted from compiler output — re-run "
            "`frontier-scout agent compile --repo . --out .` and commit."
        )


def test_committed_guard_is_byte_identical_to_source_hook_runtime():
    # The single most important anti-drift check: the committed hook == the tested source.
    committed_guard = (REPO / ".claude" / "hooks" / "_fs_guard.py").read_text()
    assert committed_guard == Path(hook_runtime.__file__).read_text(), (
        ".claude/hooks/_fs_guard.py is stale vs hook_runtime.py — re-run `agent compile`."
    )


def test_committed_lock_matches_fresh_compile_modulo_compiled_at(tmp_path):
    _compile_committed_policy_into(tmp_path)
    committed = json.loads((REPO / "policy.lock.json").read_text())
    fresh = json.loads((tmp_path / "policy.lock.json").read_text())
    # `compiled_at` is intentionally volatile; everything else must match exactly.
    for key in ("policy_sha256", "frontier_scout_version", "targets"):
        assert committed[key] == fresh[key], f"policy.lock.json field {key!r} drifted"
    assert committed["policy_sha256"] == policy_hash(
        json.loads((REPO / "frontier-scout.policy.json").read_text())
    ), "committed lock hash does not bind the committed policy"


def test_committed_verify_workflow_is_hardened_and_secretless():
    wf = (REPO / ".github" / "workflows" / "frontier-scout-verify.yml").read_text()
    assert "permissions:" in wf and "contents: read" in wf  # least-privilege token
    assert "persist-credentials: false" in wf
    assert "fetch-depth: 0" in wf  # enough history for `verify-pr --base origin/<branch>`
    assert "agent verify-pr" in wf
    assert "--advisory" in wf  # repo runs advisory while onboarding
    assert "pip install ." in wf  # self-hosting: install from source, not PyPI
    # normal verification must not require any secrets
    assert "secrets." not in wf and "${{ secrets" not in wf


def test_compiler_workflow_template_is_hardened_and_secretless():
    # The template emitted for ALL users must also ship least-privilege hardening.
    assert "permissions:" in _WORKFLOW and "contents: read" in _WORKFLOW
    assert "persist-credentials: false" in _WORKFLOW
    assert "fetch-depth: 0" in _WORKFLOW  # base diffs need full history
    assert "agent verify-pr" in _WORKFLOW
    assert "secrets." not in _WORKFLOW and "${{ secrets" not in _WORKFLOW
