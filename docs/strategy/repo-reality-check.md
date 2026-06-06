# Frontier Scout — Repo Reality Check (Phase 1)

**Date:** 2026-06-06
**Purpose:** Ground the "AI Agent Adoption Firewall + Agent Audit Trail" MVP in *actual repo files* before
designing. Every claim below is backed by `file:line` evidence gathered by 9 parallel read-only review
agents. No guessing.

**Baseline:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` → **672 passed, 0 failed** (92s) on a
clean tree. Any new failure during this sprint is unambiguously ours.

---

## Headline finding: the MVP's five verbs are *all already taken*, and one of them executes code

The strategy memo and the user prompt name the MVP commands `scan`, `policy`, `trial`, `receipts`,
`export`, `doctor`. Five of these already exist in `cli.py` with **different — and in one case dangerous —
semantics**:

| MVP verb | Existing command | What the existing one does | Collision risk |
|---|---|---|---|
| `scan` | `scan` (cli.py:194, :751) | Live **radar tool-verdict** scan (BYO-LLM), `--dry-run` seeds offline | Different domain (tool radar, not repo risk surfaces) |
| `trial` | `trial` (cli.py:342, :1109) + `deps trial` (cli.py:334) | **EXECUTES a subprocess** in the hermetic lab / runs the repo test command | **HONESTY HAZARD** — reusing `trial` for a non-executing evaluator violates the static-only invariant |
| `policy` | `policy init` (cli.py:396, help = *"Manage local Adoption Firewall policy"*) | Writes a **TOML** tool-adoption tuning file (`.frontier-scout/policy.toml`) | Same word, totally different object (zero field overlap) |
| `doctor` | `doctor` (cli.py:162, :668) | 10 read-only install checks | Extend, don't rebuild |
| `export` | `packs export` (cli.py:298, :891) | Emits Claude managed-config | Different artifact set |

The maintainers **already treat "trial" as an execution-connoting word**: `safety_summary.py:23-26` renames
the verdict `trial` → `review` for human output *specifically because "trial reads as execution."* And the
existing `policy` command's help is literally *"Manage local Adoption Firewall policy"* — meaning **the repo
already ships a thing called "Adoption Firewall"** (the legacy `evaluate`/`trial`/`guard`/`policy` radar
slice). The user's product is *also* called "AI Agent Adoption Firewall." Two "Adoption Firewalls" is a real
disambiguation problem the design must solve.

**Design consequence (decided in Phase 2):** the MVP lives under a **new, collision-free `agent` command
group** (`agent` is confirmed unused — grep of `sub.add_parser` shows no `agent`), with the non-executing
task evaluator named **`check`** (not `trial`). This resolves every collision and the honesty hazard at once.

---

## Surface-by-surface classification

Classifications: **strategic asset** · **useful but needs refactor** · **aspirational/stale** ·
**distraction** · **unknown**.

### 1. CLI dispatch — `cli.py`, `__main__.py`, `doctor.py` → *strategic asset (extend)*
- Single-file argparse. `build_parser()` (cli.py:44-426) registers all subcommands on one
  `sub = parser.add_subparsers(dest="command")` (cli.py:78); nested groups (`packs`, `deps`, `policy`,
  `incident`) use a second `add_subparsers(dest="<group>_command")`. Dispatch is a flat
  `if args.command == "X":` ladder (cli.py:539-1178); each block **lazy-imports** its impl module and
  returns an `int` exit code.
- **No global `--json`** — each subcommand declares its own `--json` and branches `if args.json:
  print(json.dumps(...))`.
- `doctor` **already exists** (`run_doctor()` doctor.py:35-47 returns a list of `Check(ok|warn|fail, fix)`).
- **Reuse:** register `agent` as a new nested group in `build_parser()`; add one `if args.command ==
  "agent":` block before the `parser.error` fallthrough (cli.py:1178); match the per-command `--json`
  idiom and `int` exit codes (0 ok, 1 findings, 2 usage). Extend `run_doctor()` with agent-firewall checks
  rather than building a second doctor.
- *Honesty:* the CLI actively reinforces static/emit-not-enforce copy (cli.py:977, :1031-1033) and
  hard-gates unbuilt clients to a nonzero error (cli.py:895-902) — a good pattern to mirror.

### 2. Sanctioned-packs engine — `packs.py`, `pack_flow.py`, `safety_summary.py`, `mcp_audit.py` → *strategic asset (reuse directly)*
- **THE risk taxonomy to reuse verbatim.** `mcp_audit.py:13-14` defines
  `CAPABILITY_KEYS = (read, write, network, browser, shell, credential, unknown)` and
  `DANGEROUS_KEYS = everything except read`. `classify_mcp_capabilities()` (mcp_audit.py:53-105) regex-matches
  capabilities from **text only** and **fails closed**: empty/unmatched input → `unknown=likely`,
  `confidence=low` (mcp_audit.py:70-86).
- **The high-risk gate:** `RISKY_FLAGS = frozenset({write, shell, credential, network})`
  (safety_summary.py:21); `is_high_risk = RISKY_FLAGS ∩ dangerous_flags` (safety_summary.py:78-81).
- Verdict dict assembled in `build_safety_summary` (safety_summary.py:56-75):
  `category, fit, risk, readiness, source_url, verdict, ...` — the canonical schema. *(Sharp edge: in the
  pack path `readiness` is a degenerate copy of `verdict` — safety_summary.py:64 — not a 1-5 score.)*
- **Reuse:** the MVP `scan` + `check` must express risk in **these seven capability keys** and the **same
  `RISKY_FLAGS`** set — feed a proposed task's text through `classify_mcp_capabilities`, then map dangerous
  flags → `block` / `needs_approval` / `allow`, defaulting unknown → not-allow. Do **not** invent a parallel
  taxonomy.
- *Honesty:* exemplary — capabilities are classified from description/tags only (deliberately *not* from
  config keys, with a code comment explaining why, safety_summary.py:49-52); nothing executes. **Caveat:**
  `get_candidates(discover=True)` does a network fetch to the MCP registry (packs.py:458-468) — the MVP
  must stay **strictly offline** and never inherit that opt-in path.

### 3. Existing `policy.py` → *useful but needs refactor (avoid overlap)*
- Today "policy" = **5 decision-tuning booleans + a `packs` dict** (policy.py:22-27):
  `require_trial_for_dangerous_capabilities`, `fail_unknown_capabilities`,
  `allow_adopt_without_lab_for_low_risk`, `strict`, `packs`. It is the engine behind *tool adoption*, not a
  task-authorization rulebook. **Zero field overlap** with the MVP's
  `allowed_tools/blocked_tools/allowed_shell_commands/.../approval_gates`.
- `Verdict = Literal["adopt","trial","assess","hold"]` (policy.py:19) — an *adoption-tier* axis, **not**
  `allow/needs_approval/block` (a per-task *gate* axis). Serialized as **TOML** at
  `.frontier-scout/policy.toml`, loaded via `load_policy()` repo→home→default with malformed-file fallback
  (policy.py:46-68). Consumed by 6 callers (`trials`, `dossier`, `safety_summary`, `cli`, `scout_tab`,
  `tui3.data`).
- **Decision:** build a **NEW first-class pydantic model** in a **new module** + a **new file
  `frontier-scout.policy.json`**. Do **not** overload `policy.py:Policy` (would break the TOML round-trip
  and 6 consumers). The strategy memo line 190 explicitly asks for a *new* neutral policy object.
- **Reuse (not duplicate):** the `PolicyFinding` shape (`severity/rule_id/message/tool_name`, policy.py:30)
  for "reasons"; `load_policy`'s try-parse-then-default **resilience pattern**; `home_dir()` /
  in-repo-`.frontier-scout/` path idiom; `format_findings()` (guard.py:84) for text/json rendering;
  `Verdict`-style `Literal` typing (mirror as `Literal["allow","needs_approval","block"]`).
- *Lesson embedded in the code (policy.py:118-123):* `require_trial_for_dangerous_capabilities` shipped as
  dead config with no consumer until v1.2.1 — **wire every new policy field to a real consumer** or it
  becomes exactly the kind of dead config this firewall is meant to expose.

### 4. `trials.py`, `dep_trial.py`, `guard.py`, `evaluate.py` → *strategic asset (extend) + naming hazard*
- `run_trial` (trials.py:62-73) and `run_dependency_trial` (dep_trial.py:117-155) **execute subprocesses**
  (hermetic lab / repo test command). `trial` == *execute-in-sandbox* in this codebase. **The MVP `check`
  must execute nothing.**
- `guard` (guard.py:16-81) is the **no-execution evidence checker** — iterates stored manifests, emits
  `PolicyFinding` rows, renders text/json/github via `format_findings` (guard.py:84-115). Closest precedent
  for the MVP's static, non-blocking stance. *(Caveat: guard's `repo` arg is ledger-global, not
  repo-scoped — guard.py:24-30.)*
- `evaluate_url` (evaluate.py:32-83) is the **pure, no-LLM, no-execution** scorer — the exemplar pattern for
  the MVP evaluator.
- `evaluate_policy` (policy.py:87-204) is the **decision-engine shape to mirror**: ordered precedence,
  accumulate findings, fail-closed, derive one verdict. Map: block-class finding → `block`;
  dangerous-without-approval-gate → `needs_approval`; else `allow`.
- **Avoid touching** `trials.py`/`dep_trial.py`/`lab.py` — those are the execution surfaces the MVP is
  explicitly *not*.

### 5. `store.py`, `telemetry.py`, `notifications.py` (persistence/receipts) → *strategic asset (reuse directly)*
- Two scopes: **home** `~/.frontier-scout/` (`home_dir()`, store.py:13, env-override `FRONTIER_SCOUT_HOME`)
  holding `db.sqlite` + JSON/JSONL sidecars; and **in-repo** `<repo>/.frontier-scout/` holding only
  `policy.toml` (policy.py:51) and `profile.json` (cli.py:722).
- Existing receipts (`render_trial_receipt`, trials.py:104-142) are **Markdown under home**
  `~/.frontier-scout/reports/trials/<slug>.md`. The telemetry **JSONL** (telemetry.py:4-79) is the only
  thing called a "ledger" (append-only, opt-in, secret-redacted).
- **Decision:** MVP receipts are **standalone JSON, one file per decision, under `<repo>/.frontier-scout/
  receipts/`** (in-repo — travels with the repo, coherent with `frontier-scout.policy.json` also in-repo).
  **Not** SQLite, **not** Markdown. **Copy `notifications.py:25-108` almost verbatim**: timestamp-stamped
  filename (`%Y-%m-%dT%H-%M-%S-%fZ` + slug), `write_text(json.dumps(..., indent=2, default=str))`, list via
  `glob("*.json")` reverse-sorted tolerating `OSError`/`JSONDecodeError`.
- **Reuse:** `_now()` timestamp (store.py:1250), the slugify regex (trials.py:141),
  `sanitize_sensitive_text` for task/command strings before write. Call them **"receipts," never "ledger."**
- *Honesty guard (already tested):* `test_proof_variants.py:30-33` requires "static assessment" /
  "generated-by" framing and **forbids** "signed-by"/"witnessed" — mirror that language; never imply the
  task ran.

### 6. `profile.py`, `imports.py`, `scout.py`, `dossier.py` (repo profiling) → *strategic asset (reuse directly)*
- `build_scout_profile(repo)` (profile.py:442) → `ScoutProfile` (profile.py:47): a mature, **offline,
  read-only** profiler. Already detects `package.json`/`pyproject.toml`/lockfiles (`_MANIFEST_FILENAMES`,
  profile.py:74), CI (`.github/workflows`, gitlab, circle, jenkins — profile.py:506), containers, and
  **agent configs** (`.mcp.json`, `CLAUDE.md`, `AGENTS.md`, `.cursor`, `.codex`, `.claude`, `.gemini` —
  profile.py:513). Skips `_SKIP_DIRS` (node_modules/.venv/.git/.frontier-scout, profile.py:101) and **all
  dot-dirs below root** (profile.py:161).
- **The only existing risk signal is one flag: `agent-config-present` (profile.py:557).** No secret-file,
  protected-path, or deploy-config enumeration exists.
- **Reuse:** call `build_scout_profile` and read its fields; reuse `_walk_manifests` (profile.py:132) and
  `_SKIP_DIRS`. **Genuinely new work** (the MVP's substance): enumerate (a) secret-likely files **by
  name/path only — never read values** (honor `ignored_paths`, profile.py:62; `_redact_secrets` at
  scripts/prompts.py:356 if content ever surfaces); (b) protected paths (migrations, infra, deploy,
  secrets, auth, billing, security, CI, prod config); (c) files the walker misses — `.cursorrules`,
  `.windsurf/`, `.github/copilot-instructions.md`, `Makefile`, deploy config — via root-level `.exists()`
  checks (pattern at profile.py:506-526). Extend `risk_flags`, don't fork the profiler.

### 7. `exporters/claude_config.py` → *strategic asset (pattern to follow)*
- One exporter today. Pure builders (`to_managed_config`/`to_project_mcp_json`, no I/O, no redaction) + one
  thin disk wrapper (`export_claude_config`, claude_config.py:101-118) that `mkdir(parents=True)`, writes,
  and **redacts at write time** via `sanitize_sensitive_text(json.dumps(...))` (claude_config.py:116-117).
  Credential safety: `_url_pattern` uses `parsed.hostname` not `netloc` so `user:pass@` can't leak.
- **Reuse pattern:** new `exporters/policy_snippets.py` with pure
  `build_claude_md_snippet/build_agents_md_snippet/build_pr_checklist(policy) -> str`, plus one thin wrapper
  that runs every emitted string through `sanitize_sensitive_text` before `write_text`. Re-export from
  `exporters/__init__.py`. **Do NOT** route these through the `--client` hard-gate (cli.py:895) — CLAUDE.md/
  AGENTS.md/PR-checklist are *formats*, not clients. Copy must be advisory ("paste this to document the
  policy"), never implying runtime enforcement.

### 8. `platform/*`, `tui/tui2/tui3`, `report.py`, `providers/`, `wizard/`, `lab.py` → *aspirational/stale (avoid overlap)*
- `platform/*` (authz, context, evals, gateway, memory, orchestration, retrieval, tools…) is a self-contained
  OpenFGA-style **agent runtime** that exists **only** to power the parked `incident_change_scout` vertical
  (sole importer: workflow.py:9-18; gated behind `FRONTIER_SCOUT_EXPERIMENTAL`, cli.py:1147-1161).
- **TRAP (high static-vs-runtime confusion risk):** `platform/tools/registry.py` (`ToolDefinition` with
  `scope/risk/requires_approval/mcp-allowlist`) and `platform/authz/engine.py` *look* like a ready-made
  policy+trial engine — but `ToolRegistry.call()` **executes handlers** under a graph-authz runtime
  (registry.py:32-41). Reusing it would silently break the static-only invariant. **Do not import it.**
- `tui3` (5828 LoC Mission Control, the default UI), `report.py`, `providers/`, `wizard/`, `lab.py` are the
  radar "engine underneath" — real and shipping, but a **distraction for this wedge**. **Do not modify or
  extend any of these.** None is dead code; none belongs in the MVP.

### 9. Docs / metadata / CI → *useful but needs refactor (extend, surgically)*
- **Confirmed identity drift:** `pyproject.toml:8` still says *"A local AI adoption radar for tools, MCP
  servers, agent frameworks, and model drops."*, version `1.8.1` (mirrored `frontier_scout/__init__.py:3`),
  keyword `tech-radar` (pyproject.toml:20). `RELEASE_NOTES.md` only describes v0.1.0 radar + Adoption
  Firewall + Incident Change Scout (never mentions packs). `docs/release-metadata.md:7,13` still ships the
  radar description. Narrative docs (README hero, ROADMAP, AGENTS.md, DEPRECATIONS) **have** pivoted to
  sanctioned packs with honest research-preview framing.
- **Reuse, don't reinvent:** the honesty NOTE block (README.md:35) and AGENTS.md Conventions
  (AGENTS.md:86-89) are the single source of the four invariants (static-only / emit-not-enforce /
  Claude-Code-first / research-preview) — **quote them**. The `docs/examples/sanctioned-packs/README.md`
  "What this IS / is NOT" template is the pattern for a new gold-path example.
- **CI reality (important):** the named gates `make lint/type/coverage/eval/demo/audit` (Makefile:14-29) are
  **all scoped to the parked `frontier_scout/platform/*` Incident Change Scout code**; `make demo` runs
  `FRONTIER_SCOUT_EXPERIMENTAL=1 frontier-scout incident demo`. The packs product (and any new MVP) is
  covered **only** by the broad `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -m "not live" -q` step
  (ci.yml:59). So **MVP tests will run in CI automatically**, but the MVP code is **not** lint/type/coverage-
  gated unless we widen the Makefile globs. We will run `ruff`/`mypy` on the new modules **locally** and
  must **not** claim "CI-gated" beyond the pytest step. `release.yml` parses `CHANGELOG.md` by exact
  `## {version}` regex — a release needs a matching section.

---

## Reusable building blocks (the MVP's foundation)

| Need | Reuse | Location |
|---|---|---|
| Risk taxonomy | `CAPABILITY_KEYS`, `DANGEROUS_KEYS`, `classify_mcp_capabilities`, fail-closed default | `mcp_audit.py:13,53-105` |
| High-risk set | `RISKY_FLAGS = {write,shell,credential,network}` | `safety_summary.py:21` |
| Decision/reason shape | `PolicyFinding(severity,rule_id,message,tool_name)` | `policy.py:30` |
| Decision-engine pattern | `evaluate_policy` ordered-precedence + `evaluate_url` pure scorer | `policy.py:87`, `evaluate.py:32` |
| Finding rendering | `format_findings(... text|json|github)` | `guard.py:84` |
| Repo profiling | `build_scout_profile`, `_walk_manifests`, `_SKIP_DIRS`, `ignored_paths` | `profile.py:442,132,101,62` |
| Local-data roots | `home_dir()` (home) + `<repo>/.frontier-scout/` (in-repo) | `store.py:13`, `policy.py:51` |
| Receipt-per-record pattern | `notifications.py` glob/stamp/tolerant-read | `notifications.py:25-108` |
| Timestamp | `_now()` = `datetime.now(UTC).isoformat()` | `store.py:1250` |
| Slugify | `re.sub(r"[^A-Za-z0-9_.-]+","-", name).lower()` | `trials.py:141` |
| Secret redaction | `sanitize_sensitive_text` | `outputs/_text.py:53` |
| Exporter pattern | pure builder + thin redacting disk wrapper | `exporters/claude_config.py:101-118` |
| Honesty copy | README NOTE block + AGENTS Conventions + proof-variant language | `README.md:35`, `AGENTS.md:86-89` |

## Traps to avoid

1. **Do not reuse the `trial` name** for the non-executing evaluator (execution-connoting; honesty hazard).
2. **Do not overload `policy.py:Policy`** with MVP fields (breaks TOML round-trip + 6 consumers).
3. **Do not import `platform/tools/registry.py` or `platform/authz/engine.py`** — they execute handlers.
4. **Do not read secret file contents** — enumerate by name/path only.
5. **Do not inherit the packs `discover=True` network path** — the MVP stays strictly offline.
6. **Do not route snippet exporters through the `--client` gate** — they're formats, not clients.
7. **Do not claim "CI-gated"** beyond the broad pytest step without widening Makefile globs.
8. **Do not touch `tui3`/`report.py`/`platform/*`/`providers/`/`wizard/`** — off-wedge.

## Strategy-memo alignment

No contradiction with `docs/strategy/frontier-scout-strategy-research-2026.md` (the source of truth). The MVP
is a faithful instantiation of the memo's endorsed wedge (Wedge 1 firewall + Wedge 3 pack governance +
Wedge 5 audit trail), scoped to **static preflight + policy + evidence** — explicitly *not* a runtime,
sandbox, SaaS, SDLC platform, or Jira/Linear integration (all memo non-goals, all respected). The one place
the memo cautions — "do not re-headline 'firewall' as runtime enforcement" — is honored by keeping the
product **advisory/static** and surfacing it under the neutral `agent` namespace. **Proceed.**
