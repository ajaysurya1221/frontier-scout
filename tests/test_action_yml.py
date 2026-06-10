# tests/test_action_yml.py
"""Property tests for the composite GitHub Action (action.yml).

Same spirit as the dogfood golden tests: string-level invariants over committed
artifacts, no YAML dependency (the dev env deliberately has none). These lock
the Action's security posture: SHA-pinned steps, no expression interpolation
inside run bodies, no secrets, fail-closed base resolution.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ACTION = (REPO / "action.yml").read_text()
DOGFOOD_WF = (REPO / ".github" / "workflows" / "frontier-scout-verify.yml").read_text()
SMOKE_WF = (REPO / ".github" / "workflows" / "attest-smoke.yml").read_text()


def _run_block_lines(yaml_text: str) -> list[str]:
    """Lines inside `run: |` literal blocks (indentation-tracked, no YAML parser)."""
    lines = yaml_text.splitlines()
    body: list[str] = []
    block_indent: int | None = None
    for line in lines:
        if block_indent is not None:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if stripped and indent <= block_indent:
                block_indent = None  # dedent ends the block
            else:
                body.append(line)
                continue
        if re.match(r"^\s*run:\s*\|", line):
            block_indent = len(line) - len(line.lstrip(" "))
    return body


def test_action_uses_steps_are_sha_pinned():
    refs = re.findall(r"uses:\s*(\S+)", ACTION)
    assert refs, "action.yml should contain uses: steps"
    for ref in refs:
        assert re.search(r"@[0-9a-f]{40}$", ref), f"uses ref not SHA-pinned: {ref}"


def test_action_run_bodies_never_interpolate_expressions():
    # Inputs must flow via env:, never inline `${{ ... }}` inside run scripts —
    # the standard composite-action script-injection guard.
    for line in _run_block_lines(ACTION):
        assert "${{" not in line, f"expression interpolated inside a run body: {line.strip()}"


def test_action_is_secretless_and_fail_closed():
    assert "secrets." not in ACTION and "${{ secrets" not in ACTION
    # A missing base must never become an empty diff.
    assert "fail-closed" in ACTION
    assert 'exit 1' in ACTION
    # The verifier command and the evidence file are wired.
    assert "agent verify-pr" in ACTION
    assert "--json-out" in ACTION
    # Attestation never silently degrades: no continue-on-error anywhere.
    assert "continue-on-error" not in ACTION


def test_action_self_install_default():
    # Empty `version` input installs the action's own pinned-ref source.
    assert "GITHUB_ACTION_PATH" in ACTION


def test_dogfood_workflow_exercises_the_action():
    assert "uses: ./" in DOGFOOD_WF


def test_attest_smoke_workflow_is_manual_and_scoped():
    assert "workflow_dispatch" in SMOKE_WF
    assert "id-token: write" in SMOKE_WF
    assert "attestations: write" in SMOKE_WF
    assert "contents: read" in SMOKE_WF
    assert "secrets." not in SMOKE_WF
    assert 'attest: "true"' in SMOKE_WF
