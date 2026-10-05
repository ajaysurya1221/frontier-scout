# tests/test_verify_regression_matrix.py
"""Real-git regression matrix for ``verify-pr`` false acceptance paths (D1-D5).

The 38 repository cases build a temp repository with real commits and let the verifier
run the real ``git`` itself; one parser unit test and one documentation test complete the
module (40 tests). The first assertion of each bypass case is ``res.ok is False``:
on the pre-repair verifier (b9abe24) that assertion fails because the PR was accepted.
Controls (benign in-scope change, empty diff, real hook receipts) must keep passing.
The defect/test mapping lives in docs/evaluation/verifier-2026-10-06.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from frontier_scout.agent_firewall import hook_runtime as hr
from frontier_scout.agent_firewall.compile import compile_claude
from frontier_scout.agent_firewall.lock import policy_hash, read_lock, write_lock
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.agent_firewall.policy import save_policy
from frontier_scout.agent_firewall.verify import verify_pr

POLICY = AgentPolicy(
    allowed_file_globs=["src/**", "tests/**", "frontier-scout-receipts/**"],
    protected_file_globs=["**/migrations/**", ".github/workflows/**", "deploy/**"],
    allowed_shell_commands=["pytest"],
)

_SEED = {
    "src/app.py": "x = 1\n",
    "app/migrations/0001_init.py": "# schema\n",
    "deploy/run.sh": "echo deploy\n",
    "docs/notes.txt": "notes\n",
    "tools/run.sh": "echo tool\n",
    ".gitignore": ".frontier-scout/\n",
}


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch, tmp_path_factory):
    """Pin git to default behaviour: no user/system config, fixed identity."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key, value in {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }.items():
        monkeypatch.setenv(key, value)


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.root = str(path)

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True)
        return proc.stdout.decode("utf-8", "surrogateescape").strip()

    def write(self, rel: str, content: str | bytes) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    @property
    def lock_hash(self) -> str:
        return str(read_lock(str(self.path / "policy.lock.json"))["policy_sha256"])

    def local_receipt(self, name: str, receipt: dict[str, object] | str) -> None:
        """An untracked receipt in the gitignored local receipts dir (agent-side)."""
        body = receipt if isinstance(receipt, str) else json.dumps(receipt)
        self.write(f".frontier-scout/receipts/{name}.json", body)


def _make_repo(tmp_path: Path, *, compile_policy: bool = True) -> tuple[Repo, str]:
    repo = Repo(tmp_path / "repo")
    repo.path.mkdir()
    repo.git("-c", "init.defaultBranch=main", "init", "-q")
    if compile_policy:
        compile_claude(POLICY, repo=repo.root)
    for rel, content in _SEED.items():
        repo.write(rel, content)
    base = repo.commit("base")
    repo.git("checkout", "-q", "-b", "pr")
    return repo, base


def _codes(res) -> set[str]:
    return {f.code for f in res.findings}


def _receipt(ph: str | None, files: list[str], decision: str = "ask", **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "receipt_id": f"r-{decision}", "kind": "agent-action", "tool_name": "Edit",
        "decision": decision, "verdict": {"allow": "allow", "ask": "needs_approval", "deny": "block"}[decision],
        "files_considered": files,
    }
    if ph is not None:
        body["policy_hash"] = ph
    body.update(extra)
    return body


# --- controls: benign changes keep passing ----------------------------------------


def test_control_benign_in_scope_change_passes(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.write("src/app.py", "x = 2\n")
    repo.commit("in-scope edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is True
    assert res.verdict == "pass" and res.summary.startswith("PASS")
    assert res.scope == "verified" and res.approval_provenance == "not-required"
    assert res.policy_source.startswith("base ")
    assert _codes(res) == {"RECEIPT_ABSENT"}  # warning only: hooks may not be installed


def test_control_empty_diff_passes(tmp_path):
    repo, base = _make_repo(tmp_path)
    res = verify_pr(repo.root, base=base)
    assert res.ok is True and res.verdict == "pass"
    assert res.checked_files == 0 and res.findings == []


def test_control_real_hook_receipts_for_in_scope_edit_pass(tmp_path):
    repo, base = _make_repo(tmp_path)
    policy = json.loads((repo.path / "frontier-scout.policy.json").read_text())
    event = {
        "hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s", "cwd": ".",
        "tool_input": {"file_path": str(repo.path / "src" / "app.py"), "old_string": "1", "new_string": "3"},
    }
    hr.handle_pre_tool_use(event, policy=policy, policy_hash=repo.lock_hash, repo=repo.root)
    repo.write("src/app.py", "x = 3\n")
    hr.handle_post_tool_use(event, policy_hash=repo.lock_hash, repo=repo.root)
    repo.commit("agent edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is True and res.verdict == "pass"
    assert res.findings == [] and res.receipt_count == 2


def test_control_static_check_receipt_is_ignored_not_fatal(tmp_path):
    from frontier_scout.agent_firewall.decision import evaluate_task
    from frontier_scout.agent_firewall.receipts import write_receipt

    repo, base = _make_repo(tmp_path)
    write_receipt(evaluate_task("edit src/app.py", POLICY), repo=repo.root, task="edit", policy_path=None)
    repo.write("src/app.py", "x = 2\n")
    repo.commit("in-scope edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is True
    assert "RECEIPT_NOT_ACTION" in _codes(res)


@pytest.mark.parametrize("name", ["src/my file.py", "src/new\nline.py", "src/café.py"])
def test_control_odd_in_scope_filenames_pass(tmp_path, name):
    repo, base = _make_repo(tmp_path)
    repo.write(name, "y = 1\n")
    repo.commit("odd name")
    res = verify_pr(repo.root, base=base)
    assert res.ok is True and res.scope == "verified"
    assert all("\n" not in a for a in res.annotations)


def test_control_protected_change_without_receipt_fails(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.write("app/migrations/0001_init.py", "# changed\n")
    repo.commit("protected edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and res.verdict == "fail"
    assert "PROTECTED_NO_RECEIPT" in _codes(res)


def test_control_denied_action_fails(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.local_receipt("deny", _receipt(repo.lock_hash, ["src/app.py"], decision="deny"))
    repo.write("src/app.py", "x = 9\n")
    repo.commit("edit despite deny")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert "RECEIPT_DENY_BYPASS" in _codes(res)


# --- D1: allowed_file_globs was never enforced --------------------------------------


def test_d1_out_of_scope_addition_fails(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.write("scripts/exfil.sh", "curl example.invalid\n")
    repo.commit("out of scope")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert res.verdict == "fail" and res.scope == "violated"
    assert "SCOPE_OUTSIDE_ALLOWED" in _codes(res)


def test_d1_out_of_scope_deletion_fails(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.git("rm", "-q", "docs/notes.txt")
    repo.commit("delete out of scope")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert "SCOPE_OUTSIDE_ALLOWED" in _codes(res)


def test_d1_out_of_scope_advisory_is_visibly_advisory(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.write("scripts/exfil.sh", "x\n")
    repo.commit("out of scope")
    res = verify_pr(repo.root, base=base, advisory=True)
    assert not res.summary.startswith("PASS")  # an advisory run must not read as a pass
    assert res.ok is True and res.advisory is True  # advisory never blocks
    assert res.verdict == "fail" and "advisory" in res.summary.lower()
    assert res.violations == [] and any("SCOPE_OUTSIDE_ALLOWED" in w for w in res.warnings)
    assert all(a.startswith("::warning") for a in res.annotations)


# --- D2: any receipt naming the file counted as approval ----------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"decision": "ask"},
        {"decision": "allow"},
        {"decision": "allow", "realized": {"completed": True}},
        {"decision": "ask", "approval_source": "human-reviewer", "approved_by": "maintainer"},
    ],
    ids=["ask", "allow", "realized", "self-declared-approval"],
)
def test_d2_local_receipt_cannot_authorise_protected_change(tmp_path, extra):
    repo, base = _make_repo(tmp_path)
    extra = dict(extra)
    decision = str(extra.pop("decision"))
    repo.local_receipt("claim", _receipt(repo.lock_hash, ["app/migrations/0001_init.py"], decision, **extra))
    repo.write("app/migrations/0001_init.py", "# drop table\n")
    repo.commit("protected edit with a local receipt")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert res.verdict == "unverified" and res.unverified is True
    assert "APPROVAL_UNAUTHENTICATED" in _codes(res)
    assert any("approval provenance not authenticated" in v for v in res.violations)
    # Scope and approval provenance are reported separately.
    assert res.scope == "verified" and res.approval_provenance == "unauthenticated"
    assert "PASS" not in res.summary


# --- D3: receipts without policy_hash skipped the stale check -----------------------


def test_d3_receipt_without_policy_hash_is_rejected(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.local_receipt("unbound", _receipt(None, ["src/app.py"], decision="allow"))
    repo.write("src/app.py", "x = 4\n")
    repo.commit("in-scope edit, unbound receipt")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert "RECEIPT_POLICY_HASH_MISSING" in _codes(res)


def test_d3_unbound_receipt_cannot_cover_protected_change(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.local_receipt("unbound", _receipt(None, ["app/migrations/0001_init.py"]))
    repo.write("app/migrations/0001_init.py", "# changed\n")
    repo.commit("protected edit, unbound receipt")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert {"RECEIPT_POLICY_HASH_MISSING", "APPROVAL_UNAUTHENTICATED"} <= _codes(res)


def test_d3_control_stale_receipt_still_rejected(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.local_receipt("stale", _receipt("0" * 64, ["src/app.py"], decision="allow"))
    repo.write("src/app.py", "x = 5\n")
    repo.commit("edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "RECEIPT_STALE" in _codes(res)


# --- D4: receipts committed inside the PR were indistinguishable --------------------


def test_d4_forged_approval_receipt_committed_in_pr_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    forged = _receipt(repo.lock_hash, ["app/migrations/0002_drop.py"], "ask", approval_source="maintainer")
    repo.write("frontier-scout-receipts/forged.json", json.dumps(forged))
    repo.write("app/migrations/0002_drop.py", "# drop everything\n")
    repo.commit("migration + its own approval receipt")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert res.verdict != "pass"
    assert {"APPROVAL_UNAUTHENTICATED", "RECEIPT_IN_PR"} <= _codes(res)
    assert res.receipts_in_pr == 1
    assert any("app/migrations/0002_drop.py" in v and "approval provenance not authenticated" in v
               for v in res.violations)


def test_d4_malformed_receipt_never_passes(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.local_receipt("broken", "{not json")
    repo.write("src/app.py", "x = 6\n")
    repo.commit("edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "RECEIPT_MALFORMED" in _codes(res)


# --- D5: diff collection (renames, deletions, modes, binaries, names, failures) -----


def test_d5_rename_escape_of_protected_file_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.git("mv", "app/migrations/0001_init.py", "src/0001_init.py")
    repo.commit("move the migration out of the protected dir")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert any(f.code == "PROTECTED_NO_RECEIPT" and f.path == "app/migrations/0001_init.py" for f in res.findings)


def test_d5_rename_out_of_scope_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    (repo.path / "scripts").mkdir()
    repo.git("mv", "src/app.py", "scripts/app.py")
    repo.commit("rename out of scope")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert any(f.code == "SCOPE_OUTSIDE_ALLOWED" and f.path == "scripts/app.py" for f in res.findings)


def test_d5_control_protected_deletion_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.git("rm", "-q", "deploy/run.sh")
    repo.commit("delete protected")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "PROTECTED_NO_RECEIPT" in _codes(res)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_d5_mode_only_change_out_of_scope_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    os.chmod(repo.path / "tools" / "run.sh", 0o755)
    repo.commit("chmod +x")
    assert repo.git("diff", "--name-status", f"{base}...HEAD") == "M\ttools/run.sh"
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "SCOPE_OUTSIDE_ALLOWED" in _codes(res)


def test_d5_binary_file_out_of_scope_is_violation(tmp_path):
    repo, base = _make_repo(tmp_path)
    repo.write("assets/blob.bin", bytes(range(256)))
    repo.commit("binary")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "SCOPE_OUTSIDE_ALLOWED" in _codes(res)


@pytest.mark.parametrize(
    "name",
    [".github/workflows/café.yml", ".github/workflows/tab\there.yml",
     ".github/workflows/new\nline.yml", '.github/workflows/quo"te.yml'],
    ids=["non-ascii", "tab", "newline", "quote"],
)
def test_d5_odd_filename_in_protected_path_is_caught(tmp_path, name):
    repo, base = _make_repo(tmp_path)
    repo.write(name, "on: push\n")
    repo.commit("odd protected name")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    # The raw name is matched; the exported path field shows control characters escaped.
    shown = name.replace("\t", "\\t").replace("\n", "\\n")
    assert any(f.code == "PROTECTED_NO_RECEIPT" and f.path == shown for f in res.findings)
    # A newline in a file name must never start a new workflow command line.
    assert all("\n" not in a and "\r" not in a for a in res.annotations)
    assert all("\n" not in v for v in res.violations)


def test_d5_control_failed_diff_collection_is_not_pass(tmp_path):
    repo, _ = _make_repo(tmp_path)
    res = verify_pr(repo.root, base="no-such-ref-0000")
    assert res.ok is False and res.verdict == "unverified"
    assert "DIFF_FAILED" in _codes(res)


def test_d5_missing_base_is_not_pass(tmp_path):
    repo, _ = _make_repo(tmp_path)
    repo.write("scripts/exfil.sh", "x\n")
    repo.commit("out of scope")
    res = verify_pr(repo.root)  # no base: nothing was diffed
    assert res.ok is False
    assert res.verdict == "unverified" and "DIFF_BASE_MISSING" in _codes(res)


def test_d5_option_shaped_base_is_rejected_not_executed(tmp_path):
    repo, _ = _make_repo(tmp_path)
    sentinel = tmp_path / "written-by-git"
    res = verify_pr(repo.root, base=f"--output={sentinel}")
    assert res.ok is False
    assert "DIFF_BASE_INVALID" in _codes(res)
    assert not list(tmp_path.glob("written-by-git*"))  # git never saw it as an option


# --- trusted base: the PR cannot expand its own authorisation ----------------------


def test_policy_and_lock_self_expansion_is_governed_by_base(tmp_path):
    repo, base = _make_repo(tmp_path)
    expanded = POLICY.model_copy(update={
        "allowed_file_globs": [*POLICY.allowed_file_globs, "scripts/**", "**"],
        "protected_file_globs": [".github/workflows/**"],
    })
    save_policy(expanded, str(repo.path / "frontier-scout.policy.json"))
    write_lock(expanded, repo.root, targets=["claude"])
    repo.write("scripts/x.sh", "x\n")
    repo.write("app/migrations/0002.py", "# x\n")
    repo.commit("expand own policy + lock consistently")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    codes = _codes(res)
    assert {"SCOPE_OUTSIDE_ALLOWED", "PROTECTED_NO_RECEIPT", "POLICY_CHANGED_IN_PR"} <= codes
    assert any(f.path == "frontier-scout.policy.json" and f.code == "PROTECTED_NO_RECEIPT" for f in res.findings)
    assert any(f.path == "policy.lock.json" and f.code == "PROTECTED_NO_RECEIPT" for f in res.findings)
    assert res.policy_source == f"base {base[:12]}"


def test_pr_cannot_introduce_its_own_policy_when_base_has_none(tmp_path):
    repo, base = _make_repo(tmp_path, compile_policy=False)
    save_policy(POLICY, str(repo.path / "frontier-scout.policy.json"))
    write_lock(POLICY, repo.root, targets=["claude"])
    repo.write("src/app.py", "x = 7\n")
    repo.commit("bring my own policy")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "POLICY_LOCK_MISSING" in _codes(res)
    assert res.scope == "not-evaluated"


def test_malformed_lock_identity_never_passes(tmp_path):
    repo, _ = _make_repo(tmp_path)
    (repo.path / "policy.lock.json").write_text(json.dumps({"frontier_scout_version": "2.1.0"}))
    base = repo.commit("lock without a policy hash")
    repo.write("src/app.py", "x = 8\n")
    repo.commit("edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "POLICY_LOCK_MALFORMED" in _codes(res)


def test_malformed_policy_never_passes(tmp_path):
    repo, _ = _make_repo(tmp_path)
    bad = {"version": 1, "allowed_file_globs": "src/**"}  # wrong type: schema-invalid
    (repo.path / "frontier-scout.policy.json").write_text(json.dumps(bad))
    lock = json.loads((repo.path / "policy.lock.json").read_text())
    lock["policy_sha256"] = policy_hash(bad)  # identity matches, content is still invalid
    (repo.path / "policy.lock.json").write_text(json.dumps(lock))
    base = repo.commit("schema-invalid policy")
    repo.write("src/app.py", "x = 9\n")
    repo.commit("edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False and "POLICY_MALFORMED" in _codes(res)


def test_every_reason_code_is_documented():
    from frontier_scout.agent_firewall.verify import REASON_CODES

    doc = (Path(__file__).resolve().parents[1] / "docs" / "evaluation" / "verifier-2026-10-06.md").read_text()
    for code, (outcome, _meaning) in REASON_CODES.items():
        assert f"| `{code}` | {outcome} |" in doc, f"{code} missing from the reason-code table"


# --- parser and receipt-shape units ---------------------------------------------------


def test_name_status_parser_handles_every_status_and_rejects_unknown():
    from frontier_scout.agent_firewall.verify import DiffChange, GitDiffError, _parse_name_status_z

    raw = b"M\0a b\0A\0new\nline\0D\0gone\0T\0link\0R087\0old/p\0new/p\0C100\0src\0dst\0"
    assert _parse_name_status_z(raw) == [
        DiffChange("M", ("a b",)), DiffChange("A", ("new\nline",)), DiffChange("D", ("gone",)),
        DiffChange("T", ("link",)), DiffChange("R", ("old/p", "new/p")), DiffChange("C", ("src", "dst")),
    ]
    assert _parse_name_status_z(b"") == []
    assert _parse_name_status_z(b"A\0caf\xff.txt\0")[0].paths == ("caf\udcff.txt",)  # non-UTF-8 kept
    for bad in (b"U\0x\0", b"X\0x\0", b"R100\0only-one\0", b"M\0", b"M\0\0"):
        with pytest.raises(GitDiffError) as exc:
            _parse_name_status_z(bad)
        assert exc.value.code == "DIFF_UNPARSEABLE"


def test_block_verdict_counts_as_deny_and_bad_shapes_are_malformed(tmp_path):
    repo, base = _make_repo(tmp_path)
    ph = repo.lock_hash
    repo.local_receipt("blk", {**_receipt(ph, ["src/app.py"], "allow"), "verdict": "block"})
    repo.local_receipt("kind", {**_receipt(ph, ["src/app.py"], "allow"), "kind": "made-up"})
    repo.local_receipt("files", {**_receipt(ph, ["src/app.py"], "allow"), "files_considered": "src/app.py"})
    repo.local_receipt("list", "[1, 2]")
    repo.write("src/app.py", "x = 10\n")
    repo.commit("edit")
    res = verify_pr(repo.root, base=base)
    assert res.ok is False
    assert "RECEIPT_DENY_BYPASS" in _codes(res)
    assert sum(1 for f in res.findings if f.code == "RECEIPT_MALFORMED") == 3
