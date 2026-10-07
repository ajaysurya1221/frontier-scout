# tests/test_action_isolation.py
"""Adversarial execution tests: the Action never runs Python from the candidate checkout.

On a PR run the workspace holds the candidate (PR) checkout. The candidate repository built
here carries shadow modules at its root (``pip.py``, ``json.py``, ``uuid.py``, ``argparse.py``,
``subprocess.py``, ``pydantic.py``, ``sitecustomize.py``, ``usercustomize.py``, and
``frontier_scout/`` and ``outputs/`` packages). Each one writes a marker file when imported.

The tests extract the run steps verbatim from ``action.yml`` (no YAML dependency) and execute
them the way the runner does: ``bash --noprofile --norc -eo pipefail``, the step's ``env:``
with its expressions substituted, and the step's ``working-directory``. ``PYTHONPATH`` points
at the candidate as well, so isolation must also ignore the environment. Each step runs twice:
from its declared working directory, and from inside the candidate checkout (as if the
``working-directory`` line were dropped), so ``python -I`` alone is shown to be sufficient.
No marker may appear. A control runs the pre-fix command forms from the checkout and shows
the shadows do execute there, so the fixtures are live.

The install step runs offline (``PIP_NO_INDEX``) against the already installed
``frontier-scout`` version, so it resolves without changing the test environment. The
``version: ""`` branch (build from ``$GITHUB_ACTION_PATH``) needs a build backend, so here it
is covered by the static checks in ``tests/test_action_yml.py`` only; the
``action-source-install`` job in ``.github/workflows/ci.yml`` runs it on a GitHub-hosted runner.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ACTION = (REPO / "action.yml").read_text()

SHADOW_MODULES = (
    "pip.py", "json.py", "uuid.py", "argparse.py", "subprocess.py", "pydantic.py",
    "sitecustomize.py", "usercustomize.py",
    "frontier_scout/__init__.py", "frontier_scout/__main__.py", "frontier_scout/cli.py",
    "outputs/__init__.py", "outputs/_text.py",
)
_EXPR = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")


# --- action.yml run steps, extracted without a YAML parser ---------------------------


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(value: str) -> str:
    value = value.strip()
    if value[:1] in ("'", '"'):
        return value[1 : value.index(value[0], 1)]
    return value.split(" #", 1)[0].strip()


def action_steps(text: str = ACTION) -> list[dict]:
    """``runs.steps`` of the composite action: scalar keys, ``env``/``with`` maps, ``run``."""

    lines = text.splitlines()
    start = lines.index("runs:")
    steps: list[dict] = []
    current: dict | None = None
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("    - "):
            current = {}
            steps.append(current)
            line = "      " + line[6:]
        stripped = line.strip()
        if current is None or not stripped or stripped.startswith("#") or _indent(line) != 6:
            i += 1
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        i += 1
        if key == "run" and value == "|":
            body: list[str] = []
            while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) >= 8):
                body.append(lines[i][8:])
                i += 1
            current["run"] = "\n".join(body).rstrip("\n") + "\n"
        elif key in ("env", "with") and not value:
            mapping: dict[str, str] = {}
            while i < len(lines) and lines[i].strip() and _indent(lines[i]) >= 8:
                k, _, v = lines[i].strip().partition(":")
                mapping[k.strip()] = _scalar(v)
                i += 1
            current[key] = mapping
        else:
            current[key] = _scalar(value)
    return steps


def _run_steps() -> dict[str, dict]:
    return {s["name"]: s for s in action_steps() if "run" in s}


def test_parser_sees_every_run_step():
    steps = action_steps()
    assert [s["name"] for s in steps if "run" in s] == [
        "Install frontier-scout", "Verify PR scope (fail-closed)", "Build attestation predicate",
        "Enforce verdict",
    ]
    assert ACTION.count("run: |") == 4
    assert all("uses" in s or "run" in s for s in steps)


# --- simulated runner ----------------------------------------------------------------


def _expand(value: str, ctx: dict[str, str]) -> str:
    def sub(match: re.Match[str]) -> str:
        expr = match.group(1)
        if expr not in ctx:
            raise AssertionError(f"unexpected expression in action.yml: {expr}")
        return ctx[expr]

    return _EXPR.sub(sub, value)


def _parse_outputs(path: Path) -> dict[str, str]:
    lines = path.read_text().splitlines() if path.exists() else []
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        if "<<" in lines[i]:
            name, delim = lines[i].split("<<", 1)
            end = lines.index(delim, i + 1)
            out[name] = "\n".join(lines[i + 1 : end])
            i = end + 1
        else:
            name, _, value = lines[i].partition("=")
            out[name] = value
            i += 1
    return out


class Runner:
    def __init__(self, tmp_path: Path, candidate: Path, markers: Path) -> None:
        self.tmp = tmp_path
        self.candidate = candidate
        self.markers = markers
        self.temp = tmp_path / "runner_temp"
        self.temp.mkdir()
        self.summary = tmp_path / "step_summary.md"
        home = tmp_path / "home"
        home.mkdir()
        self.env = {
            "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GITHUB_WORKSPACE": str(candidate),
            "GITHUB_ACTION_PATH": str(REPO),
            "RUNNER_TEMP": str(self.temp),
            "GITHUB_STEP_SUMMARY": str(self.summary),
            # Environment-borne injection attempts: -I must ignore PYTHON* variables.
            "PYTHONPATH": str(candidate),
            "PYTHONSTARTUP": str(candidate / "sitecustomize.py"),
            # Offline, non-mutating install: the installed version is already satisfied.
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
        self.calls = 0

    def run(
        self, step: dict, ctx: dict[str, str], *, cwd: Path | None = None
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        self.calls += 1
        env = dict(self.env)
        env.update({k: _expand(v, ctx) for k, v in step.get("env", {}).items()})
        output = self.tmp / f"github_output_{self.calls}"
        env["GITHUB_OUTPUT"] = str(output)
        declared = Path(_expand(step["working-directory"], ctx)) if "working-directory" in step else self.candidate
        script = self.tmp / f"step_{self.calls}.sh"
        script.write_text(step["run"])
        proc = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=cwd or declared, env=env, capture_output=True, text=True, timeout=120,
        )
        return proc, _parse_outputs(output)

    def fired(self) -> list[str]:
        return sorted(p.name for p in self.markers.iterdir())


def _git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    proc = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env)
    return proc.stdout.strip()


@pytest.fixture
def candidate(tmp_path: Path) -> tuple[Path, Path, str]:
    """A candidate checkout whose PR commit adds shadow modules at the repository root.
    The base commit has no policy, so the honest verdict is FAIL."""

    markers = tmp_path / "markers"
    markers.mkdir()
    root = tmp_path / "workspace"
    root.mkdir()
    _git(root, "-c", "init.defaultBranch=main", "init", "-q")
    (root / "README.md").write_text("base\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    for rel in SHADOW_MODULES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        marker = markers / rel.replace("/", "__")
        # On import: leave a marker, then try to forge a passing result.
        target.write_text(
            f"open({str(marker)!r}, 'w').write('imported')\n"
            "def load(*a, **k):\n    return {'ok': True, 'verdict': 'pass', 'summary': 'PASS'}\n"
            "def main(*a, **k):\n    return 0\n"
        )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "PR adds shadow modules")
    return root, markers, base


def _ctx(runner: Runner, inputs: dict[str, str], outputs: dict[str, str] | None = None) -> dict[str, str]:
    defaults = {"base": "", "receipts": "", "advisory": "false", "repo": ".", "version": "",
                "attest": "false", "evidence-path": "", "evidence-artifact": "", "python-version": "3.12"}
    ctx = {f"inputs.{k}": v for k, v in {**defaults, **inputs}.items()}
    ctx["runner.temp"] = str(runner.temp)
    for k, v in (outputs or {}).items():
        ctx[f"steps.verify.outputs.{k}"] = v
    return ctx


@pytest.mark.parametrize("where", ["declared", "checkout"])
def test_action_steps_never_execute_candidate_python(tmp_path, candidate, where):
    root, markers, base = candidate
    runner = Runner(tmp_path, root, markers)
    cwd = root if where == "checkout" else None
    steps = _run_steps()
    version = importlib.metadata.version("frontier-scout")

    # Install: the real pip resolves the pinned version, the real package reports it.
    proc, _ = runner.run(steps["Install frontier-scout"], _ctx(runner, {"version": version}), cwd=cwd)
    assert runner.fired() == []
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith(f"frontier-scout {version}")

    # Verify + output helper: the honest FAIL survives (a shadowed json.load would say pass).
    inputs = {"base": base, "attest": "true"}
    proc, outputs = runner.run(steps["Verify PR scope (fail-closed)"], _ctx(runner, inputs), cwd=cwd)
    assert runner.fired() == []
    assert proc.returncode == 0, proc.stderr
    assert outputs["verdict"] == "fail" and outputs["ok"] == "false"
    assert outputs["exit-code"] == "1"
    evidence = Path(outputs["evidence-path"])
    assert evidence == runner.temp / "frontier-scout-evidence.json"
    data = json.loads(evidence.read_text())
    assert data["verdict"] == "fail" and "POLICY_LOCK_MISSING" in data["reason_codes"]
    assert "::error::[POLICY_LOCK_MISSING]" in proc.stdout
    assert runner.summary.read_text().startswith("### Frontier Scout verify-pr: FAIL (enforcing)")

    # Attestation predicate helper.
    proc, pred_out = runner.run(steps["Build attestation predicate"], _ctx(runner, inputs, outputs), cwd=cwd)
    assert runner.fired() == []
    assert proc.returncode == 0, proc.stderr
    predicate = json.loads(Path(pred_out["path"]).read_text())
    assert predicate == {"verifier": "frontier-scout/verify-pr", "mode": "enforcing", "verdict": "fail"}

    # Enforcement uses the captured exit code.
    proc, _ = runner.run(steps["Enforce verdict"], _ctx(runner, inputs, outputs), cwd=cwd)
    assert proc.returncode == 1 and "did not pass (exit 1" in proc.stdout
    assert runner.fired() == []


def test_relative_repo_evidence_and_receipts_are_anchored_in_the_checkout(tmp_path, candidate):
    root, markers, base = candidate
    runner = Runner(tmp_path, root, markers)
    # A decoy next to the step's working directory must not be picked up as a receipt.
    (runner.temp / "frontier-scout-receipts").mkdir()
    (runner.temp / "frontier-scout-receipts" / "decoy.json").write_text("{}")
    (root / "frontier-scout-receipts").mkdir()
    (root / "frontier-scout-receipts" / "real.json").write_text("not json")
    inputs = {"base": base, "repo": ".", "evidence-path": "out/evidence.json",
              "receipts": "frontier-scout-receipts/*.json", "advisory": "true"}
    proc, outputs = runner.run(_run_steps()["Verify PR scope (fail-closed)"], _ctx(runner, inputs))
    assert runner.fired() == []
    assert proc.returncode == 0, proc.stderr
    assert Path(outputs["evidence-path"]) == root / "out" / "evidence.json"
    assert outputs["verdict"] == "fail" and outputs["ok"] == "true" and outputs["exit-code"] == "0"
    data = json.loads((root / "out" / "evidence.json").read_text())
    assert data["receipt_count"] == 1
    assert [f["path"] for f in data["findings"] if f["code"] == "RECEIPT_MALFORMED"] == [
        "frontier-scout-receipts/real.json"
    ]


def test_stale_evidence_is_removed_before_the_verifier_runs(tmp_path, candidate):
    root, markers, base = candidate
    runner = Runner(tmp_path, root, markers)
    stale = runner.temp / "frontier-scout-evidence.json"
    stale.write_text(json.dumps({"ok": True, "verdict": "pass"}))
    # A verifier that crashes before writing evidence: the stale PASS must not be read back.
    crashing = tmp_path / "crashing-python"
    crashing.mkdir()
    (crashing / "python").write_text("#!/bin/sh\nexit 3\n")
    (crashing / "python").chmod(0o755)
    runner.env["PATH"] = str(crashing) + os.pathsep + runner.env["PATH"]
    proc, outputs = runner.run(_run_steps()["Verify PR scope (fail-closed)"], _ctx(runner, {"base": base}))
    assert proc.returncode == 3
    assert "no evidence JSON was produced" in proc.stdout
    assert not stale.exists() and outputs == {}


def test_control_unisolated_forms_do_run_candidate_code(tmp_path, candidate):
    """Liveness check for the fixtures: the pre-fix command forms, run from the checkout,
    import the candidate's pip.py and json.py."""

    root, markers, _ = candidate
    runner = Runner(tmp_path, root, markers)
    env = {**runner.env, "PYTHONPATH": ""}
    subprocess.run(["bash", "-c", 'python -m pip --version'], cwd=root, env=env, capture_output=True)
    subprocess.run(["bash", "-c", "python3 - <<'PY'\nimport json\nPY"], cwd=root, env=env, capture_output=True)
    assert {"pip.py", "json.py"} <= set(runner.fired())
