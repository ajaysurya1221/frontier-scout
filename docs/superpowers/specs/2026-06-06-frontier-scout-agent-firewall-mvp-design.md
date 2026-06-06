# Design Spec — Frontier Scout Agent Adoption Firewall + Audit Trail (MVP)

**Date:** 2026-06-06 · **Status:** approved direction (user pre-approved; reality check found no
contradiction) · **Branch:** `feat/agent-firewall-mvp`

**Read first:** [`docs/strategy/repo-reality-check.md`](../../strategy/repo-reality-check.md) (Phase 1) and
[`docs/strategy/frontier-scout-strategy-research-2026.md`](../../strategy/frontier-scout-strategy-research-2026.md)
(strategy source of truth).

---

## 1. Product framing (one paragraph)

> Frontier Scout is a local-first CLI that helps teams safely adopt AI coding agents by **scanning a repo for
> agent-relevant risk surfaces**, **generating a conservative agent policy**, **evaluating proposed agent
> tasks against that policy** (allow / needs-approval / block), and **recording audit receipts** a human can
> inspect. It is **static and advisory** — it never executes an agent task, never runs an MCP server, never
> reads secret values, and **emits** evidence/config; it does **not enforce** runtime policy.

This is the strategy memo's endorsed wedge (firewall + pack governance + audit trail), scoped to static
preflight + policy + evidence. It sits **beside** the existing sanctioned-packs engine, reusing its risk
taxonomy and profiler.

## 2. Exact MVP scope (in)

A new `frontier-scout agent` command group with five capabilities + a doctor extension:

1. **`agent scan`** — enumerate repo risk surfaces (agent configs, MCP config, CI, deploy config,
   secret-likely files *by name only*, protected paths) + detected test/lint/build checks. Human + `--json`.
2. **`agent policy init`** — generate a **conservative** starter `frontier-scout.policy.json` from a scan.
3. **`agent policy explain`** — render a policy in human-readable form (+ `--json`).
4. **`agent check "<task text>"`** — evaluate a proposed agent task against the policy →
   `allow | needs_approval | block` with reasons. **Executes nothing.** Writes a receipt.
5. **`agent receipts list` / `agent receipts show <id>`** — inspect local audit receipts.
6. **`agent export claude | agents-md | pr-checklist`** — emit an **advisory** policy snippet.
7. **`doctor`** (extend existing) — add checks: policy present, policy valid, receipts dir writable.

## 3. Non-goals (out) — load-bearing

- ❌ No runtime enforcement / kill-switch. `block` is **advisory output**, not a hook that stops anything.
- ❌ No execution of the proposed task, no MCP server execution, no sandbox/lab. (Reuse of `trials.py` /
  `lab.py` / `platform/tools/registry.py` is **forbidden** — they execute code.)
- ❌ No network, no LLM, no provider. Strictly **offline + keyless**. (Do not inherit packs `discover=True`.)
- ❌ No reading of secret file **contents** — enumerate secret-likely files by **name/path only**.
- ❌ No SaaS, no web dashboard, no TUI changes, no Jira/Linear, no autonomous SDLC plane (memo non-goals).
- ❌ No new third-party dependency. Use pydantic (already present) + stdlib `json`.
- ❌ No overloading of `policy.py:Policy`, no new `scan`/`trial`/`policy` top-level verbs.
- ❌ No "enterprise / compliance / complete protection" claims.

## 4. CLI commands (chosen names + mapping to the user's recommended shape)

The user's recommended verbs collide with existing commands; per the user's explicit allowance
("preserve the existing style and document the chosen names"), the MVP is namespaced under `agent`:

| User-recommended | **MVP command** | Why renamed |
|---|---|---|
| `frontier-scout scan` | `frontier-scout agent scan` | `scan` = radar tool-verdict scan (cli.py:194) |
| `frontier-scout scan --json` | `frontier-scout agent scan --json` | per-command `--json` (no global flag) |
| `frontier-scout policy init` | `frontier-scout agent policy init` | `policy` = TOML tool-adoption tuning (cli.py:396) |
| `frontier-scout policy explain` | `frontier-scout agent policy explain` | — |
| `frontier-scout trial "<task>"` | `frontier-scout agent check "<task>"` | `trial` **executes** a subprocess (honesty hazard) |
| `frontier-scout trial --policy … --changed-files …` | `frontier-scout agent check --policy … --changed-files …` | — |
| `frontier-scout receipts list` | `frontier-scout agent receipts list` | — |
| `frontier-scout receipts show <id>` | `frontier-scout agent receipts show <id>` | — |
| `frontier-scout export claude` | `frontier-scout agent export claude` | `export` = packs export (cli.py:298) |
| `frontier-scout export agents-md` | `frontier-scout agent export agents-md` | — |
| `frontier-scout doctor` | `frontier-scout doctor` (extended) | already exists; extend `run_doctor()` |

Flags: `--repo .` (default cwd), `--policy <path>` (default `<repo>/frontier-scout.policy.json`),
`--changed-files <paths...>`, `--json`, `--path <out>` (policy init), `--force`, `--target <dir>` (export).
Exit codes follow the repo convention: **0** ok / allow, **1** findings present / fail / block (for `check`,
exit `block`→2? — decision below), **2** usage / needs-approval-or-block gate. **Decision:** `agent check`
exits **0** for `allow`, **3** for `needs_approval`, **4** for `block` so CI can branch on the verdict; all
documented. `agent scan` exits **0** always (reporting), **1** if any `high` surface found and `--strict`.

## 5. Module layout (new code only)

```
frontier_scout/agent_firewall/
  __init__.py        # public re-exports
  models.py          # pydantic: AgentPolicy, RiskSurface, ScanResult, TaskDecision, Receipt
  scan.py            # scan_repo(repo) -> ScanResult   (reuses build_scout_profile + new enumeration)
  policy.py          # generate_policy(scan) -> AgentPolicy; load_policy(path); save_policy; explain_policy
  decision.py        # evaluate_task(task, policy, changed_files) -> TaskDecision   (the `check` engine)
  receipts.py        # receipts_dir(repo); write_receipt; list_receipts; show_receipt
frontier_scout/exporters/
  policy_snippets.py # build_claude_md_snippet / build_agents_md_snippet / build_pr_checklist + export wrapper
```
Plus: new `agent` group in `cli.py` (`build_parser` + one dispatch block); new checks in `doctor.py`;
re-export snippet builders from `exporters/__init__.py`.

**Reuse imports (do not duplicate):** `from frontier_scout.mcp_audit import classify_mcp_capabilities,
CAPABILITY_KEYS, DANGEROUS_KEYS`; `from frontier_scout.safety_summary import RISKY_FLAGS`; `from
frontier_scout.policy import PolicyFinding` (the reason shape); `from frontier_scout.profile import
build_scout_profile, _SKIP_DIRS`; `from frontier_scout.store import home_dir, _now`; `from outputs._text
import sanitize_sensitive_text`.

## 6. Data model (pydantic, in `models.py`)

```python
Severity = Literal["info", "low", "medium", "high"]
Verdict  = Literal["allow", "needs_approval", "block"]

class RiskSurface(BaseModel):
    path: str                      # repo-relative
    kind: str                      # agent-config | mcp-config | ci | deploy-config | secret-likely | protected-path | build-manifest
    risk: Severity
    reason: str
    policy_implication: str        # what the policy should do about it
    suggested_checks: list[str] = []

class ScanResult(BaseModel):
    repo: str
    surfaces: list[RiskSurface] = []
    detected_checks: list[str] = []   # e.g. ["pytest", "ruff check .", "npm test"]
    counts: dict[str, int] = {}       # risk -> count
    static_only: bool = True          # honesty marker, always True

class AgentPolicy(BaseModel):
    version: int = 1
    allowed_tools: list[str] = []
    blocked_tools: list[str] = []
    allowed_shell_commands: list[str] = []
    blocked_shell_commands: list[str] = []
    allowed_file_globs: list[str] = []
    protected_file_globs: list[str] = []
    mcp_server_allowlist: list[str] = []
    required_checks: list[str] = []
    approval_gates: list[str] = []     # tokens: network|shell|credential|browser|write|protected-path|ci|deploy
    policy_notes: str = ""

class TaskDecision(BaseModel):
    verdict: Verdict
    summary: str
    reasons: list[PolicyFinding] = []  # reuse policy.PolicyFinding (severity/rule_id/message/tool_name)
    capabilities: dict[str, str] = {}  # from classify_mcp_capabilities
    dangerous_flags: list[str] = []
    files_considered: list[str] = []
    required_checks: list[str] = []
    warnings: list[str] = []
    static_only: bool = True

class Receipt(BaseModel):
    receipt_id: str                    # "<YYYY-MM-DDTHH-MM-SS-ffffffZ>-<slug>"
    timestamp: str                     # _now() ISO-8601 UTC
    repo: str
    git_branch: str | None = None
    git_commit: str | None = None
    task_summary: str
    policy_path: str | None = None
    verdict: Verdict
    reasons: list[dict] = []
    files_considered: list[str] = []
    required_checks: list[str] = []
    warnings: list[str] = []
    frontier_scout_version: str | None = None
    kind: Literal["static-policy-assessment"] = "static-policy-assessment"  # honesty marker
```

## 7. Policy format & file

- File: **`frontier-scout.policy.json`** at repo root (in-repo, travels with the repo). JSON, pydantic-backed.
- `load_policy(path)` mirrors `policy.load_policy` resilience: parse → on `OSError`/`ValueError`/validation
  error, return a conservative default **and** a warning (never crash).
- `save_policy(policy, path)` writes `json.dumps(model_dump(), indent=2)` (+ trailing newline).
- **`approval_gates` vocabulary** (the evaluator understands exactly these tokens):
  `network`, `shell`, `credential`, `browser`, `write` (capability flags from `mcp_audit`) +
  `protected-path`, `ci`, `deploy` (surface tokens). Unknown tokens are preserved but ignored by the engine
  (and surfaced by `policy explain` as "not enforced by check").

## 8. Conservative policy generation rules (`generate_policy(scan)`)

Safe-by-default. From scan results:

- **protected_file_globs** ⊇ defaults + detected: `**/.env`, `**/.env.*`, `**/*.pem`, `**/*.key`,
  `**/id_rsa`, `**/credentials*`, `**/.npmrc`, `**/.pypirc`, `**/secrets/**`, `.github/workflows/**`,
  `**/migrations/**`, `**/alembic/**`, `infra/**`, `deploy/**`, `**/*.tf`, `**/k8s/**`, `**/helm/**`,
  `**/Dockerfile`, `**/docker-compose*.y*ml`, plus any protected/secret/ci/deploy surface paths found.
- **blocked_shell_commands** (conservative defaults): `rm -rf`, `sudo`, `chmod 777`, `git push --force`,
  `git push -f`, `curl | sh`, `curl | bash`, `wget | sh`, `eval`, `:(){`, `mkfs`, `dd if=`, `> /dev/sda`.
  (Matched as case-insensitive substrings of the task text.)
- **blocked_tools**: `[]` by default (rely on approval gates), with a `policy_notes` hint.
- **allowed_shell_commands**: read-only + detected checks: `ls`, `cat`, `git status`, `git diff`,
  `git log`, `grep`, `find`, `pytest`, `ruff`, `mypy`, `black`, + the scan's `detected_checks`.
- **allowed_file_globs**: `["src/**", "tests/**", "**/*.py", "**/*.md"]` ∪ common source dirs found
  (protected globs always take precedence at evaluation time).
- **mcp_server_allowlist**: `[]` (deny-by-default; any MCP reference → needs_approval until a human adds).
- **required_checks**: the scan's `detected_checks` (e.g. `["pytest", "ruff check ."]`).
- **approval_gates**: `["network", "shell", "credential", "write", "protected-path", "ci", "deploy"]`.
- **policy_notes**: "Conservative starter generated by `frontier-scout agent policy init`. Advisory only —
  Frontier Scout emits this policy; it does not enforce it at runtime. Review and tighten before relying on
  it."

## 9. Trial (check) decision rules (`evaluate_task`) — deterministic, fail-closed, no execution

Inputs: `task` (str), `policy` (AgentPolicy), `changed_files` (list[str] | None).

1. **Capabilities:** `caps, dangerous_flags = classify_mcp_capabilities(task)` (reuse). Record both.
2. **Accumulate findings** (each a `PolicyFinding(severity, rule_id, message)`):
   - blocked tool referenced in task → `rule_id="tool.blocked"`, severity `high`, **block-class**.
   - blocked shell command substring in task → `rule_id="shell.blocked"`, `high`, **block-class**.
   - dangerous_flag ∈ `RISKY_FLAGS` and the flag-token ∈ `policy.approval_gates` → `rule_id=
     "capability.<flag>"`, `medium`, **approval-class**.
   - dangerous_flag ∈ `RISKY_FLAGS` but **not** in approval_gates and **not** blocked → `info` note (allowed
     but surfaced).
   - `unknown` capability likely (couldn't classify a non-trivial task) → `rule_id="capability.unknown"`,
     `medium`, **approval-class** (fail-closed).
   - MCP server name referenced in task not in `mcp_server_allowlist` → `rule_id="mcp.not_allowlisted"`,
     `medium`, **approval-class**.
   - changed_file matches `protected_file_globs` → `rule_id="path.protected"`, `high`, **approval-class**
     (escalate to block-class only if also matches a blocked rule). Gate token `protected-path`/`ci`/`deploy`
     in approval_gates controls whether it is approval-class (default: yes).
   - changed_file matches an `allowed_file_globs` and nothing protected → `info`.
3. **Derive verdict (precedence, fail-closed):**
   `block` if any **block-class** finding; else `needs_approval` if any **approval-class** finding; else
   `allow`. Pure read-only inspection tasks with no dangerous flags and no protected files → `allow`.
4. **Output** a `TaskDecision` with `required_checks = policy.required_checks` and a `summary`.
   `evaluate_task` **must not** call any subprocess, network, or LLM.

## 10. Receipt format & storage

- Dir: `<repo>/.frontier-scout/receipts/` (created on demand; the dir is already scan-excluded — profile.py:122).
- One JSON file per decision: `<receipt_id>.json`, `receipt_id = "<timestamp>-<slug(task)>"`.
- `write_receipt(decision, *, repo, policy_path, task)`: build `Receipt`, run `task_summary` and any string
  fields through `sanitize_sensitive_text`, `write_text(json.dumps(model_dump(), indent=2, default=str))`.
- git metadata: a guarded helper runs `git rev-parse --abbrev-ref HEAD` / `--short HEAD` read-only;
  any failure → `None` (no crash, no requirement that the repo is a git repo).
- `list_receipts(repo)`: `glob("*.json")` reverse-sorted, tolerant of `OSError`/`JSONDecodeError`.
- `show_receipt(repo, receipt_id)`: load one by id/stem; `None` if missing.
- **Honesty:** `kind="static-policy-assessment"`; render as an assessment record; **never** imply the task
  ran; **never** use "signed-by"/"witnessed"/"enforced" (guarded by `test_proof_variants` precedent).

## 11. Exporters (advisory snippets)

Pure builders returning `str`, each wrapped through `sanitize_sensitive_text` at the write boundary:
- `build_claude_md_snippet(policy)` — markdown block (allowed/blocked tools, protected paths, approval
  gates, required checks) with an "Advisory — Frontier Scout emits this; it does not enforce it" header.
- `build_agents_md_snippet(policy)` — same content tuned for AGENTS.md.
- `build_pr_checklist(policy)` — `- [ ]` checklist of required_checks + approval-gate reminders.
- `export_policy_snippets(policy, target_dir)` thin wrapper: mkdir, write each redacted snippet, return
  `{name: path}`. **Not** routed through the `--client` hard-gate (these are formats, not clients).

## 12. Doctor extension

Add to `run_doctor()` (read-only Checks): (a) `agent-policy-present` (warn + fix `agent policy init` if
absent in cwd); (b) `agent-policy-valid` (fail if present but unparseable); (c) `agent-receipts-writable`
(warn if `<repo>/.frontier-scout/` not writable). Keep emoji/text rendering as-is (doctor is plain CLI).

## 13. Test strategy (TDD — red → green → refactor)

All tests land in the broad CI step (no `live` marker). Isolate with `tmp_path` repos +
`monkeypatch.setenv("FRONTIER_SCOUT_HOME", tmp)`. New files:

- `tests/test_agent_scan.py` — detects each surface kind on a fixture repo; **asserts secret file contents
  are never read/emitted**; respects `_SKIP_DIRS`; `--json` shape; detected_checks.
- `tests/test_agent_policy.py` — `generate_policy` protects secrets/CI/deploy/migrations; load/save
  round-trip; **malformed file → safe default + warning, never crash**; `explain` output.
- `tests/test_agent_decision.py` — table of tasks → expected verdict: blocked cmd → block; protected-path
  change → needs_approval; unknown/dangerous → needs_approval (fail-closed); read-only → allow;
  **asserts no subprocess is spawned** (monkeypatch guard).
- `tests/test_agent_receipts.py` — write/list/show round-trip; all required fields present; secret in task
  redacted; corrupt-file tolerance; git metadata optional.
- `tests/test_agent_exporters.py` — snippet sections present; planted secret redacted in output; advisory
  framing present; **no "enforce"/"signed-by" language**.
- `tests/test_agent_cli.py` — `agent scan/policy init/check/receipts list+show/export` via `cli.main(argv)`;
  exit codes (allow 0 / needs_approval 3 / block 4); `--json` parseable.
- `tests/test_agent_honesty.py` — copy guards: scan/check/receipt output contains "static"/"advisory",
  never "enforce"/"guarantee"/"signed-by"/"witnessed"; `static_only is True` everywhere.

## 14. Docs updates

- **README.md** — new section "Agent adoption firewall + audit trail (research preview)" under the existing
  demand-gated framing (not a second hero): what it is / who it's for / problem solved / 60-second
  quickstart / what it is **not** / safety caveats / example workflow / the command-mapping table.
- **ROADMAP.md** — slot the MVP into the existing roadmap with research-preview framing.
- **pyproject.toml** — update the drifted `description` (drop radar-only identity; describe packs + agent
  governance honestly). **No version bump** (no release this sprint). Drop/keep `tech-radar` keyword: add
  `agent-governance`. (Surgical.)
- **DEPRECATIONS.md** — record the "Adoption Firewall" disambiguation (see §15) and that `agent` is the new
  static product surface.
- **CHANGELOG.md** — add an `Unreleased` entry for the agent firewall MVP.
- **docs/examples/agent-firewall/** — gold-path example (sample `frontier-scout.policy.json`, a scan
  excerpt, a `check` decision, a receipt, the three snippets) + a "What this IS / is NOT" README mirroring
  `docs/examples/sanctioned-packs/`.
- **docs/strategy/security-review.md** (Phase 6) and **docs/strategy/autonomous-implementation-report.md**
  (Phase 7).

## 15. Migration / deprecation decisions for stale surfaces

1. **"Adoption Firewall" name clash** — the repo already labels the legacy `evaluate`/`trial`/`guard`/
   `policy` radar slice "Adoption Firewall" (cli.py:396 help). **Decision:** the *new* static `agent` group
   is the product going forward; the legacy commands are left **functionally untouched** (no risky help-text
   renames that could break tests) but documented in DEPRECATIONS.md as the *legacy radar policy engine*,
   distinct from the new static agent firewall. No legacy behavior changes.
2. **Parked surfaces** (`platform/*`, `incident_change_scout`, `tui*`, `report.py`, `providers/`, `wizard/`,
   `lab.py`) — untouched; explicitly out of MVP scope. The MVP never imports the executing
   `platform/tools/registry.py` / `platform/authz/engine.py`.
3. **Metadata drift** (RELEASE_NOTES.md, docs/release-metadata.md) — noted; RELEASE_NOTES is a release-time
   artifact, so this sprint updates README/ROADMAP/pyproject/CHANGELOG and **flags** the rest in the final
   report rather than doing a full release rewrite (out of scope; no release this sprint).
4. **CI gating** — MVP tests ride the broad pytest step (automatic). The MVP code is **not** lint/type/
   coverage-gated by the platform-scoped Makefile targets. **Decision:** run `ruff`/`mypy` on the new
   modules **locally** during verification and report results honestly; optionally widen `make lint`/`make
   type` to include `frontier_scout/agent_firewall/` (low-risk, deferred to implementation judgment). Do not
   claim "CI-gated" beyond pytest.

## 16. Definition of done (from the user)

A user can: install/run locally → `agent scan` a repo → `agent policy init` (conservative policy) →
`agent check "<task>"` (allow/needs_approval/block) → `agent receipts show` → read a README explaining the
new product and its non-claims → run `pytest` for the core behavior. All honesty invariants hold; baseline
672 tests still green; new tests green.
