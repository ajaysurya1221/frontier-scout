# Agent Adoption Firewall + Audit Trail MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Tests use
> `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest`.

**Goal:** Add a static, advisory `frontier-scout agent` command group that scans a repo for agent risk
surfaces, generates a conservative `frontier-scout.policy.json`, evaluates proposed agent tasks
(allow/needs_approval/block) without executing them, records JSON audit receipts, and emits advisory policy
snippets.

**Architecture:** A new `frontier_scout/agent_firewall/` package + one `exporters/policy_snippets.py`,
wired into the existing argparse CLI as a nested `agent` group. Reuses the existing risk taxonomy
(`mcp_audit`), high-risk set (`safety_summary.RISKY_FLAGS`), finding shape (`policy.PolicyFinding`), repo
profiler (`profile.build_scout_profile`), local-data roots (`store.home_dir`), and redaction
(`outputs._text.sanitize_sensitive_text`). Strictly offline, keyless, static — executes nothing.

**Tech Stack:** Python 3.11+, pydantic (already a dependency), stdlib `json`/`fnmatch`/`pathlib`. No new deps.

**Conventions (from reality check):** per-command `--json` (no global flag); int exit codes; lazy-import impl
modules in the CLI dispatch block; `from __future__ import annotations`; pydantic `BaseModel` snake_case;
secret-safety = name/path only + `sanitize_sensitive_text` at every write boundary.

**Reviewer note:** implementer subagents WRITE files + RUN their task's tests, but do **NOT** `git commit`.
The controller runs the full suite + lint/type and commits coherently after reviews pass.

---

### Task 1: Data models (`agent_firewall/models.py`)

**Files:**
- Create: `frontier_scout/agent_firewall/__init__.py`
- Create: `frontier_scout/agent_firewall/models.py`
- Test: `tests/test_agent_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_models.py
from frontier_scout.agent_firewall.models import (
    AgentPolicy, RiskSurface, ScanResult, TaskDecision, Receipt,
)


def test_agent_policy_defaults_are_empty_and_versioned():
    p = AgentPolicy()
    assert p.version == 1
    for field in (
        "allowed_tools", "blocked_tools", "allowed_shell_commands",
        "blocked_shell_commands", "allowed_file_globs", "protected_file_globs",
        "mcp_server_allowlist", "required_checks", "approval_gates",
    ):
        assert getattr(p, field) == []
    assert p.policy_notes == ""


def test_agent_policy_round_trips_through_json():
    p = AgentPolicy(blocked_shell_commands=["rm -rf"], approval_gates=["shell"])
    again = AgentPolicy.model_validate(p.model_dump())
    assert again == p


def test_models_carry_static_only_honesty_markers():
    assert ScanResult(repo=".").static_only is True
    assert TaskDecision(verdict="allow", summary="ok").static_only is True
    assert Receipt(
        receipt_id="x", timestamp="t", repo=".", task_summary="s", verdict="allow"
    ).kind == "static-policy-assessment"


def test_risk_surface_requires_core_fields():
    s = RiskSurface(path=".env", kind="secret-likely", risk="high",
                    reason="r", policy_implication="i")
    assert s.suggested_checks == []
    assert s.risk == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_agent_models.py -q`
Expected: FAIL (ModuleNotFoundError: frontier_scout.agent_firewall).

- [ ] **Step 3: Write minimal implementation**

```python
# frontier_scout/agent_firewall/__init__.py
"""Static, advisory AI-agent adoption firewall + audit trail (research preview)."""
```

```python
# frontier_scout/agent_firewall/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from frontier_scout.policy import PolicyFinding  # reuse the canonical finding shape

Severity = Literal["info", "low", "medium", "high"]
Verdict = Literal["allow", "needs_approval", "block"]


class RiskSurface(BaseModel):
    path: str
    kind: str
    risk: Severity
    reason: str
    policy_implication: str
    suggested_checks: list[str] = Field(default_factory=list)


class ScanResult(BaseModel):
    repo: str
    surfaces: list[RiskSurface] = Field(default_factory=list)
    detected_checks: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    static_only: bool = True


class AgentPolicy(BaseModel):
    version: int = 1
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    allowed_shell_commands: list[str] = Field(default_factory=list)
    blocked_shell_commands: list[str] = Field(default_factory=list)
    allowed_file_globs: list[str] = Field(default_factory=list)
    protected_file_globs: list[str] = Field(default_factory=list)
    mcp_server_allowlist: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    approval_gates: list[str] = Field(default_factory=list)
    policy_notes: str = ""


class TaskDecision(BaseModel):
    verdict: Verdict
    summary: str
    reasons: list[PolicyFinding] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)
    dangerous_flags: list[str] = Field(default_factory=list)
    files_considered: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    static_only: bool = True


class Receipt(BaseModel):
    receipt_id: str
    timestamp: str
    repo: str
    git_branch: str | None = None
    git_commit: str | None = None
    task_summary: str
    policy_path: str | None = None
    verdict: Verdict
    reasons: list[dict] = Field(default_factory=list)
    files_considered: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    frontier_scout_version: str | None = None
    kind: Literal["static-policy-assessment"] = "static-policy-assessment"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest tests/test_agent_models.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Report DONE** (do not commit — controller commits).

---

### Task 2: Repo risk scanner (`agent_firewall/scan.py`)

**Files:**
- Create: `frontier_scout/agent_firewall/scan.py`
- Test: `tests/test_agent_scan.py`

**Reuse:** `from frontier_scout.profile import build_scout_profile, _SKIP_DIRS`. Detect via root-level
`(repo / name).exists()` checks (the walker skips dot-dirs, so `.cursor`/`.github`/`.windsurf` need explicit
checks). **Never open secret files** — match by name/path only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_scan.py
from pathlib import Path

from frontier_scout.agent_firewall.scan import scan_repo
from frontier_scout.agent_firewall.models import ScanResult


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# instructions\n")
    (tmp_path / ".cursorrules").write_text("rules\n")
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {}}\n')
    (tmp_path / ".env").write_text("SECRET_TOKEN=sk-ant-SHOULD-NOT-BE-READ\n")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\n")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_init.sql").write_text("CREATE TABLE x;\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
    pkg = tmp_path / "pyproject.toml"
    pkg.write_text("[project]\nname='x'\n")
    return tmp_path


def test_scan_detects_each_surface_kind(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert isinstance(result, ScanResult)
    kinds = {s.kind for s in result.surfaces}
    assert {"agent-config", "mcp-config", "ci", "secret-likely",
            "protected-path", "deploy-config"} <= kinds
    paths = {s.path for s in result.surfaces}
    assert "CLAUDE.md" in paths and ".cursorrules" in paths
    assert ".env" in paths and ".github/workflows" in {p.rstrip("/") for p in paths} or \
        any(p.startswith(".github") for p in paths)


def test_scan_never_reads_secret_file_contents(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    blob = result.model_dump_json()
    assert "sk-ant-SHOULD-NOT-BE-READ" not in blob
    assert "SECRET_TOKEN" not in blob
    env = next(s for s in result.surfaces if s.path == ".env")
    assert env.kind == "secret-likely" and env.risk == "high"


def test_scan_detects_checks_from_manifests(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert any("pytest" in c for c in result.detected_checks)


def test_scan_counts_by_risk(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert sum(result.counts.values()) == len(result.surfaces)
    assert result.static_only is True
```

- [ ] **Step 2: Run test, verify it fails** —
`pytest tests/test_agent_scan.py -q` → FAIL (no module).

- [ ] **Step 3: Write minimal implementation**

Implement `scan_repo(repo: str) -> ScanResult` that:
1. Calls `build_scout_profile(repo)` (read-only; gives languages/ci/containers/agent_configs/dependencies).
2. Enumerates surfaces with **root-level existence checks** (the walker misses dot-dirs):
   - agent configs (`risk="info"`): `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.cursor`,
     `.windsurf`, `.claude`, `.codex`, `.gemini`, `.github/copilot-instructions.md`.
   - mcp config (`risk="medium"`): `.mcp.json`, `mcp.json`, `.vscode/mcp.json`.
   - ci (`risk="high"`): `.github/workflows`, `.gitlab-ci.yml`, `bitbucket-pipelines.yml`, `Jenkinsfile`,
     `circle.yml`, `.circleci`, `buildspec.yml`, `azure-pipelines.yml`.
   - deploy-config (`risk="high"`): `Dockerfile`, `docker-compose.yml`/`.yaml`, `serverless.yml`,
     `fly.toml`, `vercel.json`, `Procfile`, any `*.tf` at root, `k8s`, `helm`, `charts`, `infra`, `deploy`.
   - protected-path (`risk="high"`): dirs `migrations`, `alembic`, `auth`, `billing`, `security`,
     `secrets`, `terraform`, plus the ci/deploy/secret paths above (a path may appear once under its most
     specific kind).
   - secret-likely (`risk="high"`, **name/path only**): top-2-level scan for `.env`, `.env.*`, `*.pem`,
     `*.key`, `id_rsa`, `id_dsa`, `credentials*`, `.npmrc`, `.pypirc`, `.netrc`, `*.p12`,
     `service-account*.json`. Use `os.scandir` bounded to depth 2, pruning `_SKIP_DIRS`. **Do not read
     file contents.**
   - build-manifest (`risk="info"`): `pyproject.toml`, `package.json`, `Makefile`, `requirements.txt`.
3. Each surface gets a `reason` + `policy_implication` (e.g. secret-likely → "Never allow agents to read or
   modify; add to protected_file_globs and blocked surfaces") + `suggested_checks` where relevant.
4. `detected_checks`: derive from profile + manifests — if `pyproject.toml`/`pytest.ini`/`tox.ini` present
   add `"pytest"`; if `ruff`/`[tool.ruff]` referenced add `"ruff check ."`; if `package.json` has a
   `"test"` script add `"npm test"`; if `Makefile` has a `test:` target add `"make test"`. Read manifest
   text is allowed (they are not secret files); guard with try/except.
5. `counts` = surfaces grouped by `risk`. Set `static_only=True`. Never raise on a single bad path
   (swallow `OSError`).

Provide a module constant `__all__ = ["scan_repo"]`.

- [ ] **Step 4: Run test, verify PASS** — `pytest tests/test_agent_scan.py -q` → PASS (4).

- [ ] **Step 5: Refactor** — extract the surface tables to module-level frozensets/dicts; re-run tests.

- [ ] **Step 6: Report DONE** (no commit).

---

### Task 3: Policy model I/O + conservative generation (`agent_firewall/policy.py`)

**Files:**
- Create: `frontier_scout/agent_firewall/policy.py`
- Test: `tests/test_agent_policy.py`

**Reuse:** the `load_policy` resilience pattern (try-parse → conservative default + warning, never crash).
Default policy path = `<repo>/frontier-scout.policy.json`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_policy.py
import json
from pathlib import Path

from frontier_scout.agent_firewall.models import AgentPolicy, ScanResult, RiskSurface
from frontier_scout.agent_firewall.policy import (
    default_policy_path, generate_policy, load_policy, save_policy, explain_policy,
)


def _scan() -> ScanResult:
    return ScanResult(
        repo=".",
        surfaces=[
            RiskSurface(path=".env", kind="secret-likely", risk="high",
                        reason="r", policy_implication="i"),
            RiskSurface(path=".github/workflows", kind="ci", risk="high",
                        reason="r", policy_implication="i"),
            RiskSurface(path="migrations", kind="protected-path", risk="high",
                        reason="r", policy_implication="i"),
        ],
        detected_checks=["pytest", "ruff check ."],
    )


def test_generate_policy_is_conservative():
    p = generate_policy(_scan())
    # protects secrets, CI, migrations
    assert any(".env" in g for g in p.protected_file_globs)
    assert any(".github/workflows" in g for g in p.protected_file_globs)
    assert any("migrations" in g for g in p.protected_file_globs)
    # blocks dangerous shell by default
    assert any("rm -rf" in c for c in p.blocked_shell_commands)
    # deny-by-default MCP allowlist
    assert p.mcp_server_allowlist == []
    # surfaces detected checks as required
    assert "pytest" in p.required_checks
    # gates the risky capability surfaces
    assert {"shell", "credential", "protected-path"} <= set(p.approval_gates)
    assert "Advisory" in p.policy_notes or "advisory" in p.policy_notes


def test_save_and_load_round_trip(tmp_path):
    p = generate_policy(_scan())
    path = tmp_path / "frontier-scout.policy.json"
    save_policy(p, str(path))
    loaded, warnings = load_policy(str(path))
    assert loaded == p and warnings == []


def test_load_missing_file_returns_default_with_warning(tmp_path):
    loaded, warnings = load_policy(str(tmp_path / "nope.json"))
    assert isinstance(loaded, AgentPolicy)
    assert warnings and "not found" in warnings[0].lower()


def test_load_malformed_file_never_crashes(tmp_path):
    bad = tmp_path / "frontier-scout.policy.json"
    bad.write_text("{ this is not json")
    loaded, warnings = load_policy(str(bad))
    assert isinstance(loaded, AgentPolicy)
    assert warnings  # surfaced, not raised


def test_default_policy_path_is_repo_root():
    assert default_policy_path("/x/y").endswith("/x/y/frontier-scout.policy.json")


def test_explain_policy_mentions_advisory_and_gates():
    text = explain_policy(generate_policy(_scan()))
    assert "advisory" in text.lower()
    assert "approval" in text.lower()
```

- [ ] **Step 2: Run test, verify FAIL** — no module.

- [ ] **Step 3: Write minimal implementation** per design §7–§8:
  - `default_policy_path(repo)` → `os.path.join(repo, "frontier-scout.policy.json")`.
  - `generate_policy(scan)` builds the conservative `AgentPolicy` (protected globs = DEFAULT_PROTECTED ∪
    scan ci/deploy/secret/protected paths as globs; `blocked_shell_commands = DEFAULT_BLOCKED_SHELL`;
    `allowed_shell_commands = DEFAULT_ALLOWED_SHELL ∪ scan.detected_checks`;
    `allowed_file_globs = ["src/**","tests/**","**/*.py","**/*.md"]`; `mcp_server_allowlist=[]`;
    `required_checks = scan.detected_checks`; `approval_gates = ["network","shell","credential","write",
    "protected-path","ci","deploy"]`; the advisory `policy_notes`). Convert a scan path to a glob: a dir →
    `"<path>/**"`; a file → `"<path>"`; `.env` family → `"**/.env*"`.
  - `save_policy(policy, path)` → `Path(path).write_text(json.dumps(policy.model_dump(), indent=2) + "\n")`.
  - `load_policy(path) -> tuple[AgentPolicy, list[str]]`: if missing → `(AgentPolicy(_conservative
    fallback_), ["policy file not found: ..."])`; on `OSError`/`json.JSONDecodeError`/`ValidationError` →
    `(AgentPolicy(), ["could not parse policy ...; using empty default"])`; else `(validated, [])`.
  - `explain_policy(policy) -> str`: human-readable summary including the word "advisory" and an
    "Approval gates" section.
  - Module constants `DEFAULT_BLOCKED_SHELL`, `DEFAULT_ALLOWED_SHELL`, `DEFAULT_PROTECTED`.

- [ ] **Step 4: Run test, verify PASS** (6).
- [ ] **Step 5: Report DONE** (no commit).

---

### Task 4: Task decision engine (`agent_firewall/decision.py`) — the `check` command

**Files:**
- Create: `frontier_scout/agent_firewall/decision.py`
- Test: `tests/test_agent_decision.py`

**Reuse:** `from frontier_scout.mcp_audit import classify_mcp_capabilities`; `from
frontier_scout.safety_summary import RISKY_FLAGS`; `from frontier_scout.policy import PolicyFinding`.
**Executes nothing.**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_decision.py
import frontier_scout.agent_firewall.decision as decision_mod
from frontier_scout.agent_firewall.decision import evaluate_task
from frontier_scout.agent_firewall.policy import generate_policy
from frontier_scout.agent_firewall.models import ScanResult


def _policy():
    return generate_policy(ScanResult(repo=".", detected_checks=["pytest"]))


def test_read_only_task_is_allowed():
    d = evaluate_task("list the files and read the README", _policy())
    assert d.verdict == "allow"
    assert d.static_only is True


def test_blocked_shell_command_is_blocked():
    d = evaluate_task("run rm -rf / to clean up", _policy())
    assert d.verdict == "block"
    assert any(r.rule_id == "shell.blocked" for r in d.reasons)


def test_protected_path_change_needs_approval():
    d = evaluate_task("update the schema",
                      _policy(), changed_files=["migrations/0002_add.sql"])
    assert d.verdict == "needs_approval"
    assert any(r.rule_id == "path.protected" for r in d.reasons)


def test_credential_capability_needs_approval():
    d = evaluate_task("read the AWS secret key from the environment and use it", _policy())
    assert d.verdict in ("needs_approval", "block")
    assert "credential" in d.dangerous_flags or any(
        "credential" in r.rule_id for r in d.reasons)


def test_required_checks_are_surfaced():
    d = evaluate_task("read a file", _policy())
    assert "pytest" in d.required_checks


def test_evaluate_task_never_spawns_a_subprocess(monkeypatch):
    import subprocess
    def _boom(*a, **k):
        raise AssertionError("evaluate_task must not execute anything")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    evaluate_task("deploy to production and run the migration", _policy(),
                  changed_files=["infra/main.tf"])
```

- [ ] **Step 2: Run test, verify FAIL** — no module.

- [ ] **Step 3: Write minimal implementation** of
  `evaluate_task(task: str, policy: AgentPolicy, changed_files: list[str] | None = None) -> TaskDecision`
  per design §9:
  - `caps, dangerous = classify_mcp_capabilities(task)` (returns dict + flags; confirm the return shape
    against `mcp_audit.py` and adapt — it may return a `PermissionManifest`; use its `.capabilities` and
    `.dangerous_flags`).
  - Build `reasons: list[PolicyFinding]`, tracking `block` flags and `approval` flags:
    - For each `cmd` in `policy.blocked_shell_commands`: if `cmd.lower()` in `task.lower()` →
      `PolicyFinding(severity="high", rule_id="shell.blocked", message=f"Task references blocked command:
      {cmd}")`, set block.
    - For each `tool` in `policy.blocked_tools`: substring match → `rule_id="tool.blocked"`, block.
    - For each `flag` in `dangerous` ∩ `RISKY_FLAGS`: if `flag` in `policy.approval_gates` →
      `rule_id=f"capability.{flag}"`, severity `medium`, set approval.
    - If `caps.get("unknown") == "likely"` and the task is non-trivial (len > 0 and no clear read-only
      signal) → `rule_id="capability.unknown"`, medium, approval (fail-closed).
    - For each `f` in `changed_files or []`: if it matches any `policy.protected_file_globs` (via
      `fnmatch.fnmatch` against the path and its `**`-normalised forms) → `rule_id="path.protected"`,
      high, approval (block only if it also matches a blocked rule).
  - Derive verdict: `block` if any block flag; elif any approval flag → `needs_approval`; else `allow`.
  - `required_checks = policy.required_checks`; `files_considered = changed_files or []`;
    `dangerous_flags = sorted(dangerous)`; `capabilities = caps`. Compose a `summary`.
  - **No subprocess / network / LLM anywhere.**

- [ ] **Step 4: Run test, verify PASS** (6).
- [ ] **Step 5: Report DONE** (no commit).

---

### Task 5: Audit receipts (`agent_firewall/receipts.py`)

**Files:**
- Create: `frontier_scout/agent_firewall/receipts.py`
- Test: `tests/test_agent_receipts.py`

**Reuse:** `from frontier_scout.store import _now`; slugify regex from `trials.py:141`;
`sanitize_sensitive_text`. Dir = `<repo>/.frontier-scout/receipts/`. Copy the `notifications.py` glob/list
pattern.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_receipts.py
from frontier_scout.agent_firewall.models import TaskDecision
from frontier_scout.agent_firewall.receipts import (
    receipts_dir, write_receipt, list_receipts, show_receipt,
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
```

- [ ] **Step 2: Run test, verify FAIL** — no module.

- [ ] **Step 3: Write minimal implementation:**
  - `receipts_dir(repo) -> Path` = `Path(repo) / ".frontier-scout" / "receipts"`.
  - `_slug(text)` = `re.sub(r"[^A-Za-z0-9_.-]+", "-", text).lower()[:40].strip("-")`.
  - `_git_meta(repo)` → guarded `subprocess.run(["git","-C",repo,"rev-parse","--abbrev-ref","HEAD"], ...)`
    and `--short HEAD`; any failure → `(None, None)`. (Read-only git query; not task execution. Wrap in
    try/except; `check=False`, `timeout=5`.)
  - `write_receipt(decision, *, repo, task, policy_path) -> str`: build `Receipt` with
    `receipt_id = f"{_now_stamp()}-{_slug(task)}"`, `timestamp=_now()`,
    `task_summary=sanitize_sensitive_text(task)[:500]`, version from `frontier_scout.__version__`,
    `reasons=[r.model_dump() for r in decision.reasons]`, git meta. Write
    `json.dumps(model_dump(), indent=2, default=str)` to `receipts_dir(repo)/f"{receipt_id}.json"`
    (mkdir parents). Return `receipt_id`. (`_now_stamp` = `datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")`.)
  - `list_receipts(repo) -> list[dict]`: `glob("*.json")` reverse-sorted; `json.loads` each, skipping
    `OSError`/`JSONDecodeError`.
  - `show_receipt(repo, receipt_id) -> dict | None`: load `<receipt_id>.json` (also accept stem match);
    `None` if missing/corrupt.

- [ ] **Step 4: Run test, verify PASS** (4).
- [ ] **Step 5: Report DONE** (no commit).

---

### Task 6: Advisory snippet exporters (`exporters/policy_snippets.py`)

**Files:**
- Create: `frontier_scout/exporters/policy_snippets.py`
- Modify: `frontier_scout/exporters/__init__.py` (re-export new builders in `__all__`)
- Test: `tests/test_agent_exporters.py`

**Reuse:** `from outputs._text import sanitize_sensitive_text`. Pure builders + redact at write. **Not**
routed through the `--client` gate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_exporters.py
from frontier_scout.agent_firewall.models import AgentPolicy
from frontier_scout.exporters.policy_snippets import (
    build_claude_md_snippet, build_agents_md_snippet, build_pr_checklist,
    export_policy_snippets,
)


def _policy():
    return AgentPolicy(
        blocked_shell_commands=["rm -rf"],
        protected_file_globs=["**/.env*", ".github/workflows/**"],
        approval_gates=["shell", "credential", "ci"],
        required_checks=["pytest", "ruff check ."],
        mcp_server_allowlist=["github"],
        policy_notes="use sk-ant-PLANTEDSECRET as the token",  # planted
    )


def test_claude_md_snippet_has_sections_and_is_advisory():
    s = build_claude_md_snippet(_policy())
    assert "advisory" in s.lower()
    assert "rm -rf" in s and ".github/workflows" in s and "pytest" in s
    assert "enforce" not in s.lower() or "does not enforce" in s.lower()


def test_pr_checklist_is_markdown_checkboxes():
    s = build_pr_checklist(_policy())
    assert "- [ ]" in s and "pytest" in s


def test_agents_md_snippet_built():
    assert "Approval gates" in build_agents_md_snippet(_policy()) or \
        "approval" in build_agents_md_snippet(_policy()).lower()


def test_export_writes_redacted_files(tmp_path):
    out = export_policy_snippets(_policy(), str(tmp_path))
    assert set(out) == {"claude", "agents-md", "pr-checklist"}
    for path in out.values():
        text = open(path).read()
        assert "sk-ant-PLANTEDSECRET" not in text  # redacted at write
```

- [ ] **Step 2: Run test, verify FAIL** — no module.

- [ ] **Step 3: Write minimal implementation:**
  - `build_claude_md_snippet(policy) -> str`: a markdown block headed
    `## Agent policy (advisory — Frontier Scout emits this; it does not enforce it)` listing Allowed tools,
    Blocked tools, Blocked shell commands, Protected paths, MCP allowlist, Approval gates, Required checks.
  - `build_agents_md_snippet(policy) -> str`: same content, AGENTS.md voice, with an "Approval gates" section.
  - `build_pr_checklist(policy) -> str`: `# Agent change checklist` + `- [ ] Run <check>` per required_check
    + `- [ ] Human approval obtained for: <gate>` per approval gate + a "static/advisory" footer.
  - `export_policy_snippets(policy, target_dir) -> dict[str,str]`: mkdir; for each `(name, builder, fname)`
    in `[("claude", build_claude_md_snippet, "CLAUDE.policy.md"), ("agents-md", build_agents_md_snippet,
    "AGENTS.policy.md"), ("pr-checklist", build_pr_checklist, "PR-CHECKLIST.md")]`, write
    `sanitize_sensitive_text(builder(policy))`; return `{name: str(path)}`.
  - Add the three builders + `export_policy_snippets` to `exporters/__init__.py` `__all__` and imports.

- [ ] **Step 4: Run test, verify PASS** (4).
- [ ] **Step 5: Report DONE** (no commit).

---

### Task 7: CLI `agent` group + doctor extension (`cli.py`, `doctor.py`)

**Files:**
- Modify: `frontier_scout/cli.py` (register `agent` group in `build_parser`; add dispatch block before the
  final `parser.error` at ~cli.py:1178)
- Modify: `frontier_scout/doctor.py` (add agent-policy checks to `run_doctor`)
- Test: `tests/test_agent_cli.py`

**Run this task ALONE** (it edits the shared `cli.py`). Lazy-import `agent_firewall` modules inside the
dispatch block. Per-command `--json`. Exit codes: `scan` 0 (1 with `--strict` and a high surface);
`policy init`/`explain` 0; `check` 0 allow / 3 needs_approval / 4 block; `receipts`/`export` 0.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_cli.py
import json

from frontier_scout.cli import main


def _seed_repo(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# x\n")
    (tmp_path / ".env").write_text("X=1\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    return str(tmp_path)


def test_agent_scan_json(tmp_path, capsys):
    repo = _seed_repo(tmp_path)
    rc = main(["agent", "scan", "--repo", repo, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["static_only"] is True
    assert any(s["path"] == ".env" for s in payload["surfaces"])


def test_agent_policy_init_writes_file(tmp_path):
    repo = _seed_repo(tmp_path)
    rc = main(["agent", "policy", "init", "--repo", repo])
    assert rc == 0
    assert (tmp_path / "frontier-scout.policy.json").exists()


def test_agent_check_block_exit_code(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "check", "run rm -rf / now", "--repo", repo])
    assert rc == 4  # block


def test_agent_check_allow_exit_and_receipt(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "check", "read the README file", "--repo", repo])
    assert rc == 0
    rc2 = main(["agent", "receipts", "list", "--repo", repo, "--json"])
    assert rc2 == 0


def test_agent_export_writes_snippets(tmp_path):
    repo = _seed_repo(tmp_path)
    main(["agent", "policy", "init", "--repo", repo])
    rc = main(["agent", "export", "claude", "--repo", repo,
               "--target", str(tmp_path / "out")])
    assert rc == 0
    assert (tmp_path / "out").exists()
```

- [ ] **Step 2: Run test, verify FAIL** — `agent` is not a command (argparse error / rc 2).

- [ ] **Step 3: Implement CLI wiring** in `build_parser`: add
  `agent_cmd = sub.add_parser("agent", help="Static, advisory AI-agent adoption firewall + audit trail.")`,
  `agent_sub = agent_cmd.add_subparsers(dest="agent_command")`. Register:
  `scan` (`--repo .`, `--json`, `--strict`); `policy` (inner sub: `init` with `--repo`,`--path`,`--force`;
  `explain` with `--repo`,`--policy`,`--json`); `check` (positional `task`, `--repo`,`--policy`,
  `--changed-files nargs="*"`,`--json`); `receipts` (inner sub: `list` `--repo`,`--json`; `show` positional
  `receipt_id` `--repo`,`--json`); `export` (positional `format` choices `claude`/`agents-md`/`pr-checklist`,
  `--repo`,`--policy`,`--target`). Add dispatch block `if args.command == "agent":` that lazy-imports the
  package modules, resolves the policy path (`--policy` or `default_policy_path(repo)`), runs the verb, prints
  human or `json.dumps(..., indent=2)`, writes a receipt for `check`, and returns the right exit code. End
  groups with `parser.error("agent ... requires a subcommand"); return 2` when no verb.

- [ ] **Step 4: Implement doctor checks** — in `doctor.py:run_doctor()` append Checks:
  `agent-policy` (cwd has `frontier-scout.policy.json`? warn+fix "frontier-scout agent policy init" if not);
  `agent-policy-valid` (if present, `load_policy` returns no warnings → ok, else fail);
  `agent-receipts-writable` (can create `<cwd>/.frontier-scout/`? ok/warn). Match the existing `Check`
  dataclass shape.

- [ ] **Step 5: Run tests, verify PASS** — `pytest tests/test_agent_cli.py tests/test_doctor.py -q`.
- [ ] **Step 6: Report DONE** (no commit).

---

### Task 8: Honesty guards + docs + gold-path example

**Files:**
- Test: `tests/test_agent_honesty.py`
- Modify: `README.md`, `ROADMAP.md`, `pyproject.toml`, `CHANGELOG.md`, `DEPRECATIONS.md`
- Create: `docs/examples/agent-firewall/README.md` + sample artifacts

- [ ] **Step 1: Write the failing honesty test**

```python
# tests/test_agent_honesty.py
from frontier_scout.agent_firewall.scan import scan_repo
from frontier_scout.agent_firewall.policy import generate_policy, explain_policy
from frontier_scout.agent_firewall.decision import evaluate_task
from frontier_scout.agent_firewall.models import ScanResult

_FORBIDDEN = ("signed-by", "witnessed", "guarantees complete", "enterprise-grade",
              "soc2", "fully secure")


def test_outputs_are_advisory_not_enforcing(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# x\n")
    scan = scan_repo(str(tmp_path))
    pol = generate_policy(scan)
    text = (explain_policy(pol) + scan.model_dump_json()).lower()
    for bad in _FORBIDDEN:
        assert bad not in text
    assert scan.static_only is True


def test_decision_is_static_only():
    d = evaluate_task("read a file", generate_policy(ScanResult(repo=".")))
    assert d.static_only is True
```

- [ ] **Step 2: Run, verify PASS** (the implementation already satisfies these — guard test). If it fails,
  fix copy in the modules, not the test.

- [ ] **Step 3: Docs (controller-owned, prose):**
  - `README.md`: add "Agent adoption firewall + audit trail (research preview)" section under the existing
    demand-gated framing — what it is / who for / problem / 60-sec quickstart (`agent scan` → `policy init`
    → `check` → `receipts show`) / what it is NOT / safety caveats / example workflow / command-mapping
    table. Quote the existing honesty NOTE block wording.
  - `ROADMAP.md`: slot the MVP with research-preview framing.
  - `pyproject.toml`: update the drifted `description` to honestly cover packs + agent governance; add an
    `agent-governance` keyword. No version bump.
  - `CHANGELOG.md`: add an `Unreleased` entry.
  - `DEPRECATIONS.md`: record the "Adoption Firewall" disambiguation (legacy radar policy/guard vs new
    static `agent` surface).
  - `docs/examples/agent-firewall/`: a `README.md` ("What this IS / is NOT" template) + sample
    `frontier-scout.policy.json`, a scan excerpt, a `check` decision, a receipt, and the three snippets.

- [ ] **Step 4: Verify** — `pytest tests/test_agent_honesty.py -q` PASS; `frontier-scout agent --help` works.
- [ ] **Step 5: Report DONE** (no commit).

---

## Post-implementation (controller, Phases 5–7)

- **Verify (Phase 5):** full suite `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` (expect 672 +
  new, 0 fail); `ruff check frontier_scout/agent_firewall frontier_scout/exporters/policy_snippets.py
  tests/test_agent_*.py`; `mypy frontier_scout/agent_firewall` (best-effort, document if env-limited);
  `frontier-scout agent --help` + a live end-to-end dry run on this repo.
- **Security & honesty review (Phase 6):** `docs/strategy/security-review.md` — secret leakage, unsafe
  shell, overclaiming, destructive ops, policy-bypass confusion, untrusted diff/path handling, receipt
  contents. Fix serious issues.
- **Final report (Phase 7):** `docs/strategy/autonomous-implementation-report.md` — all 11 required sections.
- **Commit coherently** per task group; run `git status -sb` + `detect_changes` before finishing.

## Self-review (against the design spec)

- Spec §4 commands → Tasks 2–7 ✓ · §6 models → Task 1 ✓ · §7–8 policy → Task 3 ✓ · §9 decision → Task 4 ✓ ·
  §10 receipts → Task 5 ✓ · §11 exporters → Task 6 ✓ · §12 doctor → Task 7 ✓ · §13 tests → every task ✓ ·
  §14 docs → Task 8 ✓ · §15 migration → Task 8 (DEPRECATIONS) ✓.
- Type consistency: `AgentPolicy`/`ScanResult`/`TaskDecision`/`Receipt`/`RiskSurface` names + fields are
  used identically across Tasks 1–8; `evaluate_task`/`generate_policy`/`load_policy`/`scan_repo`/
  `write_receipt` signatures match between definition and call sites.
- No placeholders: every task has full test code + concrete implementation spec + exact verification command.
