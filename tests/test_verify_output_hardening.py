# tests/test_verify_output_hardening.py
"""Output-level hardening for ``verify-pr`` (review follow-ups to the D1-D5 repair).

* Exported path fields (``Finding.path`` in the evidence JSON and the annotation
  ``file=`` property) go through the same scrubber as messages: a token-shaped file name
  is redacted everywhere, and an undecodable (non-UTF-8) file name byte is emitted as the
  marker ``\\xNN`` instead of breaking JSON emission. Matching still uses the raw name.
* A receipt whose ``decision`` or ``verdict`` is an array or object is
  ``RECEIPT_MALFORMED`` in both modes, never a ``TypeError``.

Each case builds a temp repository with real commits and runs the CLI or ``verify_pr``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from frontier_scout.agent_firewall.compile import compile_claude
from frontier_scout.agent_firewall.lock import read_lock
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.agent_firewall.verify import verify_pr
from frontier_scout.cli import main

POLICY = AgentPolicy(
    allowed_file_globs=["src/**"],
    protected_file_globs=[".github/workflows/**"],
    allowed_shell_commands=["pytest"],
)

# Synthetic and short on purpose: a token *shape* for the scrubber, not a credential.
TOKEN_NAME = "ghp_fixtureonly42"


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch, tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key, value in {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)


def _git(root: Path, *args: str | bytes, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], input=stdin, check=True, capture_output=True)
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "-c", "init.defaultBranch=main", "init", "-q")
    compile_claude(POLICY, repo=str(root))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    (root / ".gitignore").write_text(".frontier-scout/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD").decode()
    _git(root, "checkout", "-q", "-b", "pr")
    return root, base


def _run_cli(root: Path, base: str, out: Path, capsys, *extra: str) -> tuple[int, str, dict]:
    code = main(["agent", "verify-pr", "--repo", str(root), "--base", base, "--json-out", str(out), *extra])
    stdout = capsys.readouterr().out
    text = out.read_text(encoding="utf-8")
    return code, stdout, json.loads(text)


def test_token_shaped_filename_is_redacted_in_every_exported_field(tmp_path, capsys):
    root, base = _repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools" / f"{TOKEN_NAME}.txt").write_text("x\n")
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / f"{TOKEN_NAME}.yml").write_text("on: push\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "token-shaped names")

    out = tmp_path / "evidence.json"
    code, stdout, data = _run_cli(root, base, out, capsys)

    assert code == 1 and data["verdict"] == "fail"
    # The raw name was still matched: one out-of-scope path, one protected path.
    by_code = {f["code"]: f["path"] for f in data["findings"] if f["path"]}
    assert by_code["SCOPE_OUTSIDE_ALLOWED"] == "tools/ghp_REDACTED.txt"
    assert by_code["PROTECTED_NO_RECEIPT"] == ".github/workflows/ghp_REDACTED.yml"
    assert any("file=tools/ghp_REDACTED.txt::" in a for a in data["annotations"])
    for emitted in (out.read_text(encoding="utf-8"), stdout):
        assert "fixtureonly42" not in emitted
    # --json on stdout carries the same redacted result.
    assert main(["agent", "verify-pr", "--repo", str(root), "--base", base, "--json"]) == 1
    assert "fixtureonly42" not in capsys.readouterr().out


def test_undecodable_filename_bytes_serialise_with_a_marker(tmp_path, capsys):
    root, base = _repo(tmp_path)
    # Non-UTF-8 names are written straight into the index (some filesystems refuse them).
    blob = _git(root, "hash-object", "-w", "--stdin", stdin=b"x\n").decode()
    for raw in (b"tools/caf\xff.txt", b".github/workflows/bad\xfe.yml"):
        _git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob},".encode() + raw)
    _git(root, "commit", "-q", "-m", "non-utf8 names")

    out = tmp_path / "evidence.json"
    code, stdout, data = _run_cli(root, base, out, capsys)

    assert code == 1 and data["verdict"] == "fail"
    paths = {f["code"]: f["path"] for f in data["findings"] if f["path"]}
    assert paths["SCOPE_OUTSIDE_ALLOWED"] == "tools/caf\\xff.txt"
    assert paths["PROTECTED_NO_RECEIPT"] == ".github/workflows/bad\\xfe.yml"
    assert any("file=tools/caf\\xff.txt::" in line for line in stdout.splitlines())
    # Everything emitted is plain UTF-8 with no lone surrogates.
    out.read_bytes().decode("utf-8")
    stdout.encode("utf-8")
    assert main(["agent", "verify-pr", "--repo", str(root), "--base", base, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["findings"]


@pytest.mark.parametrize("advisory", [False, True], ids=["enforcing", "advisory"])
@pytest.mark.parametrize("shape", [["allow"], {"value": "allow"}], ids=["array", "object"])
@pytest.mark.parametrize("field", ["decision", "verdict"])
def test_non_string_decision_or_verdict_is_malformed_not_a_crash(tmp_path, field, shape, advisory):
    root, base = _repo(tmp_path)
    ph = str(read_lock(str(root / "policy.lock.json"))["policy_sha256"])
    receipt = {
        "receipt_id": "r-shape", "kind": "agent-action", "tool_name": "Edit", "decision": "allow",
        "verdict": "allow", "files_considered": ["src/app.py"], "policy_hash": ph, field: shape,
    }
    receipts = root / ".frontier-scout" / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "r-shape.json").write_text(json.dumps(receipt))
    (root / "src" / "app.py").write_text("x = 2\n")
    _git(root, "commit", "-q", "-am", "in-scope edit")

    res = verify_pr(str(root), base=base, advisory=advisory)

    malformed = [f for f in res.findings if f.code == "RECEIPT_MALFORMED"]
    assert len(malformed) == 1 and field in malformed[0].message
    assert res.verdict == "fail"
    if advisory:
        assert res.ok is True and res.summary.startswith("FAIL (advisory: reported, not enforced)")
        assert res.violations == [] and any("RECEIPT_MALFORMED" in w for w in res.warnings)
    else:
        assert res.ok is False and any("RECEIPT_MALFORMED" in v for v in res.violations)
