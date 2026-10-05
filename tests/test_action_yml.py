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
    # Onboarding posture is advisory by guideline; a silent flip to enforcing
    # (or removal of the advisory input) must fail this suite.
    assert 'advisory: "true"' in DOGFOOD_WF


def test_attest_smoke_workflow_is_manual_and_scoped():
    assert "workflow_dispatch" in SMOKE_WF
    assert "id-token: write" in SMOKE_WF
    assert "attestations: write" in SMOKE_WF
    assert "contents: read" in SMOKE_WF
    assert "secrets." not in SMOKE_WF
    assert 'attest: "true"' in SMOKE_WF


def test_action_reports_verdict_scope_and_provenance_separately():
    # The step outputs/summary use the verifier's own verdict (computed the same way in
    # both modes), so an advisory run with findings never reads as "pass".
    assert 'data.get("verdict")' in ACTION
    assert "approval_provenance" in ACTION and "data.get('scope'" in ACTION
    assert "never authenticate an approval" in ACTION


def _action_run_steps() -> list[tuple[str, list[str]]]:
    """(step text, run-body lines) for every `runs.steps` entry that has a `run: |` body."""
    steps_text = ACTION.split("\nruns:\n", 1)[1]
    chunks = re.split(r"\n(?=    - )", steps_text)
    out = []
    for chunk in chunks:
        if "run: |" in chunk:
            out.append((chunk, _run_block_lines(chunk)))
    return out


def _shell_lines(body: list[str]) -> list[str]:
    """Run-body lines that bash executes: heredoc contents and comments are dropped."""
    lines: list[str] = []
    terminator: str | None = None
    for line in body:
        stripped = line.strip()
        if terminator is not None:
            if stripped == terminator:
                terminator = None
            continue
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
        heredoc = re.search(r"<<-?'?([A-Z]+)'?", stripped)
        if heredoc:
            terminator = heredoc.group(1)
    return lines


def test_every_run_step_runs_outside_the_candidate_checkout():
    # The workspace holds the PR checkout; no run step may execute from it.
    steps = _action_run_steps()
    assert len(steps) == 4
    for chunk, _ in steps:
        assert "      working-directory: ${{ runner.temp }}\n" in chunk, chunk.splitlines()[0]


def test_every_python_invocation_is_isolated():
    # `python -I`: no current or script directory on sys.path, no user site, PYTHON* env
    # ignored, so a PR-root pip.py / json.py / frontier_scout/ can never be imported.
    invocations = []
    for _, body in _action_run_steps():
        for line in _shell_lines(body):
            for match in re.finditer(r"(?:^|[\s;&|(])(python[0-9.]*)(?=\s|$)", line):
                invocations.append(line)
                assert match.group(1) == "python", f"use the setup-python `python`: {line}"
                assert line[match.end():].startswith(" -I "), f"Python not isolated: {line}"
            # The console scripts (`pip`, `frontier-scout`) never run; modules go via -m.
            tokens = line.split()
            for i, token in enumerate(tokens):
                if re.fullmatch(r"pip[0-9.]*", token):
                    assert tokens[i - 3 : i] == ["python", "-I", "-m"], f"bare pip: {line}"
            assert not re.search(r"(?:^|[\s;&|(])frontier-scout(?=\s|$)", line), line
    assert len(invocations) == 6  # 2 installs, --version, verifier, 2 helpers
    assert ACTION.count("python -I - <<'PY'") == 2
    assert "python -I -m frontier_scout \"${args[@]}\"" in ACTION
    # The candidate repository reaches the verifier only as an absolute path.
    assert '*) repo="$GITHUB_WORKSPACE/$FS_REPO" ;;' in ACTION
    assert '--repo "$repo"' in ACTION
