# Frontier Scout — Current State

> **Audience:** an engineer joining cold who needs to understand this repo end to end.
> **Purpose:** an accurate, one-and-done reference for *what this is*, *how it works*, and *how it is built*.
> Every figure below was measured from the working tree (version **1.8.1**), not recalled.
> **Companion docs:** `AGENTS.md` (handoff playbook), `CLAUDE.md` (agent quick-load), `docs/architecture.md`
> + `docs/adrs/` (design decisions).

---

## 1. What it is

Frontier Scout is a **local-first, keyless-by-default CLI** (with a Textual TUI) that helps an engineering
org **adopt AI coding tools safely**. It does three things, all *static* and *offline-capable*:

1. **Sanctioned MCP packs** — repo-rank approved MCP servers, render a static capability + policy safety map,
   risk-gate a "sanction" decision, and **export a Claude Code managed-config fragment**
   (`allowedMcpServers` / `deniedMcpServers`) plus a project `.mcp.json`.
2. **Agent adoption firewall** — scan a repo's agent-risk surfaces, generate a conservative policy,
   pre-check a proposed agent task (`allow` / `needs_approval` / `block`), and keep audit receipts.
3. **Adoption radar + Mission Control** — rank and audit tools/MCP servers for a repo (the engine the packs
   ranker reuses), surfaced through an 8-tab Textual TUI.

The single most important fact: **the product is static.** It reads code *structure* (filenames + AST import
names), classifies capability and risk, and **emits** configuration and advisory artifacts. It **executes
nothing it evaluates**, and it **emits, it does not enforce** — the org's own control plane enforces. It is
shipped to GitHub Releases + PyPI and is labeled a research preview.

---

## 2. How it works (the algorithm)

All three surfaces share the same backbone: **profile the repo → score/classify candidates → decide → emit.**

### 2.1 Repo profiling (the stack graph)
`profile.build_scout_profile(repo)` → `ScoutProfile`. It walks the tree and derives:
- **Languages** and **containers** (e.g. `Dockerfile`) by file detection;
- **Agent configs** present (`.mcp.json`, `AGENTS.md`, CI workflow files);
- **Dependencies** via manifest parsing;
- **Import evidence** via `imports.py`, which uses **tree-sitter** to extract import names across languages
  (source bodies are never sent anywhere — only the import symbols).

This profile is the deterministic input every downstream stage ranks against.

### 2.2 Capability + risk classification
`mcp_audit.classify_mcp_capabilities(...)` maps a server/tool's declared capabilities into a fixed taxonomy.
`safety_summary.py` (with `RISKY_FLAGS`) renders the **static safety map**: which dangerous flags are present
(write / shell / credential / network). No server is run — this is read from registry/declared metadata.

### 2.3 Fit scoring & ranking
The radar's fit scorer ranks a candidate against the `ScoutProfile` (does this capability match the repo's
stack and needs?). `packs.py` reuses that same scorer to produce repo-ranked **pack candidates**.

### 2.4 The three decision engines (kept strictly separate)
- **Radar policy** — `policy.evaluate_policy(evaluation, manifest, lab_result=None, *, policy)` →
  `adopt` / `trial` / `assess` / `hold`. Findings accumulate from capability + manifest checks; it
  **fails closed** (no manifest, or an unknown dangerous capability, escalates).
- **Firewall task check** — `agent_firewall.evaluate_task(...)` → `allow` / `needs_approval` / `block`
  (process exit `0` / `3` / `4`). Also fail-closed: a missing/malformed policy denies; every dangerous
  capability escalates to approval.
- **Human sanction** — a person sanctions/unsanctions a server; recorded in the store.

These three verdicts are **orthogonal** and never merged into one score (see §6).

### 2.5 Sanction → export
`pack_flow.py` runs the **risk-gated** sanction: a server with a dangerous flag must show a safety summary /
`--acknowledge-risk` before it can be sanctioned; low-risk servers sanction directly. `exporters/claude_config.py`
then serializes the sanctioned set into the Claude Code managed-config fragment + `.mcp.json`.
`exporters/policy_snippets.py` emits the firewall's advisory snippets (Claude/AGENTS.md/PR-checklist formats).

### 2.6 Audit trail
The firewall writes JSON **receipts** under `<repo>/.frontier-scout/receipts/` (gitignored) for every `check`.
The radar persists scans, verdicts, evaluations, and decisions to SQLite (§6). Opt-in funnel events go to a
local JSONL ledger.

---

## 3. The three product surfaces

| Surface | CLI namespace | Executes? | Key modules |
|---|---|---|---|
| **Sanctioned MCP packs** | `frontier-scout packs …`, `stats` | **No** | `packs.py`, `pack_flow.py`, `safety_summary.py`, `exporters/claude_config.py`, `proof_variants.py` |
| **Agent adoption firewall** | `frontier-scout agent …` | **No** | `agent_firewall/` (`models`·`scan`·`policy`·`decision`·`receipts`), `exporters/policy_snippets.py` |
| **Adoption radar + Mission Control** | `scout`/`scan`/`evaluate`/`dossier`/`guard`/`trial`/`deps`/`open` | **No** | `scout.py`, `evaluate.py`, `dossier.py`, `guard.py`, `policy.py`, `profile.py`, `dependencies.py`, `tui3/` |

The packs product is the headline; the radar is the engine underneath it; the firewall is a second, parallel
static surface.

---

## 4. Repository layout & size

Measured Python LOC (excluding `.git`):

| Area | Path | Files | ~LOC | Role |
|---|---|---|---|---|
| Core engine | `frontier_scout/*.py` | 28 | 13,925 | CLI, radar, packs, store, profile, policy, providers glue |
| TUI | `frontier_scout/tui3/` | 10 | 5,828 | Mission Control (the only UI) |
| Agent firewall | `frontier_scout/agent_firewall/` | 6 | 1,095 | static adoption firewall |
| Providers | `frontier_scout/providers/` | 6 | 1,017 | LLM backend abstraction |
| Runtime substrate | `frontier_scout/platform/` | 27 | 801 | agent-runtime primitives (see §8) |
| Wizard | `frontier_scout/wizard/` | 4 | 651 | setup wizard |
| Exporters | `frontier_scout/exporters/` | 3 | 267 | Claude config + policy snippets |
| Scripts | `scripts/` | — | 5,587 | `cost_tracker`, `llm_client`, scout/lab runners |
| Outputs | `outputs/` | — | 94 | shared text utils (incl. `_text.scrub_secrets`) |
| Tests | `tests/` | 88 | 10,796 | 640 test functions |
| **Total** | | | **~36,500** | |

Other top-level dirs: `docs/` (ADRs, architecture, security model, examples), `evals/` (fixture-backed eval
sets), `demo/`, `examples/`, `infra/`, `prompts/`, `design_handoff_mission_control_v6/` (golden ASCII frames).

---

## 5. Core engine — module map

Product-path modules under `frontier_scout/` (TUI and runtime substrate excluded):

- **`cli.py`** (1,295) — argparse entry point (`frontier-scout`); every verb dispatched here, subcommands
  **lazy-imported** for cheap startup.
- **`store.py`** (1,251) — the SQLite persistence layer; schema, migrations, all reads/writes (§6).
- **`profile.py`** (1,000) — `build_scout_profile` → `ScoutProfile`, the repo stack graph.
- **`report.py`** (773) — static HTML report rendering + offline demo (`serve_demo` / `write_demo`).
- **`implement.py`** (684) — jailed executor (git-worktree + path jail + hermetic env); see §8.
- **`packs.py`** (565) — pack discovery, candidate ranking, sanction lifecycle.
- **`imports.py`** (503) — tree-sitter import-evidence scanning (multi-language).
- **`scout.py`** (460) — live scan orchestration.
- **`scheduling.py`** (403) — headless schedule executor (`cron run`).
- **`dependencies.py`** (379) — dependency-intelligence scan + upgrade findings.
- **`doctor.py`** (313) — self-diagnostics (`frontier-scout doctor`).
- **`setup_diagnostics.py`** (269) — local repo profiler powering `setup --plain` / `--json` (never leaks
  secret values).
- **`dossier.py`** (252) · **`dep_trial.py`** (247) · **`policy.py`** (204) · **`progress.py`** (190) ·
  **`pack_flow.py`** (193) · **`notifications.py`** (189) · **`evaluate.py`** (186) · **`trials.py`** (161) ·
  **`safety_summary.py`** (121) · **`guard.py`** (115) · **`mcp_audit.py`** (105) · **`telemetry.py`** (98) ·
  **`proof_variants.py`** (65) · **`preferences.py`** (49) · **`lab.py`** (16, thin shim over `scripts/`).

---

## 6. Data model

### SQLite store (`store.py`)
One SQLite DB under `$FRONTIER_SCOUT_HOME` (default `~/.frontier-scout/`). **18 tables**:

```
scans · verdicts · schema_migrations · tools · evaluations · permission_manifests ·
trial_runs · lab_results · policy_findings · adoption_decisions · policy_exceptions ·
repo_profiles · scout_graph_edges · packs · pack_candidates · dependency_findings ·
pack_overrides · dep_intel_cache
```

Migrations use an idempotent `INSERT OR IGNORE INTO schema_migrations(version, …)` pattern; DDL is written in a
portable subset (TEXT / INTEGER / REAL, ISO timestamps).

### Local ledgers (JSONL, append-only)
- `costs.jsonl` — `scripts/cost_tracker.py::log_call` writes per-call token usage + cost estimate.
- `trace.jsonl` — `platform/observability/tracing.py::SpanRecorder` writes spans (`run_id`, `trace_id`, attrs).
- `pack-events.jsonl` — `telemetry.py` writes opt-in sanctioned-pack funnel events.

### The three orthogonal verdict axes (never merged)
1. **`policy`** → `adopt` / `trial` / `assess` / `hold` (`policy.py::evaluate_policy`)
2. **`task`** → `allow` / `needs_approval` / `block`, exit `0/3/4` (`agent_firewall.evaluate_task`)
3. **`human`** → `sanctioned` / `unsanctioned` (store `adoption_decisions`)

`agent_firewall` does **not** import `policy.py`; the axes mean different things and stay separate in every
artifact. The verdict schema (`category`, `risk`, `fit`, `readiness`, `source_url`) stays aligned across the
safety summary, candidates `--json`, exporters, and tests.

---

## 7. Provider abstraction (LLM backends)

`frontier_scout/providers/`:
- **`base.py`** — the provider interface + `Usage` (token accounting).
- **`anthropic_provider.py`** — Anthropic API backend.
- **`openai_provider.py`** — OpenAI API backend.
- **`cli_provider.py`** — local CLI backends (`claude-cli`, `codex-cli`).
- **`select.py`** — backend resolution + model tiering (e.g. a `FAST` tier).
- **`__init__.py`** — exports (`FAST`, `first_tool_use`, `resolve_provider`, …).

Behavior:
- Pin a backend with `--provider anthropic|openai|claude-cli|codex-cli` (sets `FRONTIER_SCOUT_PROVIDER`;
  parsed from argv in any position).
- **Exactly one** backend is needed for live paths; `--demo` / offline and the sanctioned-pack flow need
  **none**.
- Availability **deep-probes** `<cli> --version` (cached), so a broken-but-on-PATH CLI is treated unavailable
  rather than silently selected.
- The hermetic claude-CLI scout passes `--mcp-config '{"mcpServers": {}}'` (claude 2.x rejects a bare `"{}"`).

---

## 8. The runtime substrate (`platform/` + `implement.py`)

`frontier_scout/platform/` (27 files, ~801 LOC) is an internally-consistent agent-runtime substrate:

```
authz/engine.py · context/{compiler,prompt_registry}.py · core/{budgets,config,errors,ids,types}.py ·
evals/harness.py · gateway/model_gateway.py · memory/store.py ·
observability/{audit,tracing}.py · orchestration/runtime.py (DCGRuntime) · retrieval/hybrid.py · tools/registry.py
```

It is the **only** area under mypy `strict` (`pyproject.toml` → `[tool.mypy] files = ["frontier_scout/platform"]`)
and has dedicated tests (`tests/test_platform_*.py`) mapped to an OWASP-agentic threat model
(`docs/security-model.md`). `implement.py` is the companion **jailed executor** (git-worktree + `_safe_relpath`
path jail + `_hermetic_env`; returns `ImplementResult{status, diff, exit_code, cost_usd}`), reachable via the
`implement` CLI verb and `tui3/data.py`.

---

## 9. CLI surface

Single entry point `frontier-scout` (`frontier_scout.cli:main`). A bare invocation **prints help** (it does
**not** auto-launch the TUI). Verb groups:

- **Lifecycle / diagnostics:** `init`, `setup` (`--plain` / `--json` / `--packs`), `doctor`, `clear-history`,
  `notifications {list,clear}`, `open` (explicit TUI launcher), `cron run`.
- **Radar:** `profile`, `scan` (`--dry-run`), `demo` (offline, keyless), `report`, `lab`, `evaluate`,
  `dossier`, `deps {scan,trial}`, `trial`, `implement`, `guard`, `policy init`.
- **Packs:** `packs {list,show,refresh,candidates,sanction,unsanction,export,proof}`, `stats`.
- **Firewall:** `agent {scan, policy {init,explain}, check, receipts {list,show}, export}`.

UI: `--ui mission` selects Mission Control (`tui3` — the only UI). `--demo` is a top-level alias for the
offline `demo` subcommand. Every renderable routes through `app._paint` (color↔mono) and `glyphs()`
(unicode↔ASCII); glyph-art surfaces are width-parameterized pure functions converging on golden frames.

---

## 10. Design invariants (current behavior)

Enforced by tests (`test_claim_honesty.py`, `test_agent_honesty.py`, `test_ai_radar_scope.py`):

- **Static analysis only** — the packs flow and `agent scan` / `agent check` never execute an MCP server or
  agent.
- **Emit, not enforce** — exporters produce config / advisory snippets; `block` / `hold` are advisory output,
  never a runtime kill-switch.
- **Fail closed** — a missing/malformed policy denies by default; every dangerous capability escalates to
  approval.
- **Secrets by name/path only** — secret-likely files are flagged by filename; **contents are never read**.
  Every persisted/emitted string is redacted via `outputs/_text.scrub_secrets`.
- **Offline + keyless by default**; **repo source is never sent to an LLM** (only filenames + AST import names);
  fetched release text is treated as data, never instructions.

---

## 11. Tests, CI, release

- **Tests:** 88 files, **640 test functions**. Run locally with
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q`. Three `tests/test_implement.py`
  failures are **env-only** (they shell out to `python`) and pass on CI. Some `tui3` tests run the real demo
  scan and can be slow on a cluttered local tree.
- **Convergence harness:** deterministic golden-frame + width tests (`test_tui3_golden_*`, `test_tui3_cells`,
  `test_tui3_bridging`) gate CI; `pytest-textual-snapshot` SVG snapshots are local-only (CI skips them).
- **CI (`.github/workflows/ci.yml`):** `make lint` (ruff + black) · `make type` (mypy strict, `platform/`
  only) · `detect-secrets --all-files` · `compileall` · `make coverage` · release preflight (CLI +
  deterministic demo + `python -m build`) · `make audit` · `pytest -m "not live"`.
- **Release (`.github/workflows/release.yml`):** tag-push driven (`vX.Y.Z`) → GitHub Release (draft→publish,
  immutable-safe) + PyPI (trusted publishing, gated by a `pypi` deployment environment). A wheel-content guard
  asserts the Textual `.tcss` stylesheets are bundled.
- **Makefile:** `setup`, `demo`, `test`, `coverage`, `audit`, `lint`, `type`, `ci`.

### Packaging notes
- Non-`.py` data files (Textual `theme.tcss`) **must** be declared in `pyproject.toml`
  `[tool.setuptools.package-data]` + `MANIFEST.in`, or `pip install` ships a wheel that crashes on launch.
  Verify a release against the **built wheel**, not the source tree.
- `[tool.setuptools.packages.find]` packages three top-level trees: `frontier_scout*`, `scripts*`, `outputs*`
  (so `scripts/` ships as the importable package `scripts.*` in the wheel).

---

## 12. How to run & verify (offline, keyless)

```bash
# install
make setup                       # pip install -e ".[dev]"   (use /opt/miniconda3/bin/python locally)

# see it work with zero keys / zero network
frontier-scout demo --no-serve   # deterministic offline report (--demo is a top-level alias for this)
frontier-scout open              # launch Mission Control on the current repo

# the two product surfaces, statically
frontier-scout packs candidates --repo . --client claude-code
frontier-scout agent scan --repo . --json

# full gate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -q
make ci                          # lint + type + test + coverage + audit + demo
```
