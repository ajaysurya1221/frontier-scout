# CLAUDE.md — Frontier Scout

**Read `AGENTS.md` first — it is this repo's full handoff playbook** (repo layout,
local run, test commands, conventions, definition of done, "ask before changing").
This file is the Claude Code quick-load companion: the current facts an agent needs
before touching the code.

## What this is

Frontier Scout — **sanctioned MCP-server packs for coding assistants (Claude Code
first)**, shipped as a local CLI + Textual TUI. It repo-ranks approved MCP servers into
a **static** capability + policy safety map, then **exports a Claude Code managed-config
fragment** (`allowedMcpServers` / `deniedMcpServers`, plus a project `.mcp.json`).
Keyless and offline by default. Python 3.11+, packaged with setuptools, shipped to
GitHub Releases + PyPI.

**Research preview — technically coherent, not market-validated.** It makes no
human-validation / PMF / adoption claim. The repo-aware **adoption radar** that powers
ranking and the TUI is now **the engine underneath** the packs product, not the headline
(see "The engine underneath").

## Working principles

Before editing, skim **AGENTS.md → Working principles** (think before coding · simplicity
first · surgical changes · goal-driven) — house rules for *how* to change things here, on
top of the repo-specific invariants.

## The product: sanctioned packs

The headline flow (the CLI is the artifact; runs offline + keyless on `--demo` data):

- `frontier-scout packs candidates --repo . --client claude-code` — repo-rank the
  registry's `mcp` servers for this repo (the ranker reuses the radar's fit scorer).
- **Static safety map** per server — `mcp_audit` capabilities + `policy` read, rendered
  by `safety_summary.py`. Labeled "static analysis": **no MCP server is executed.**
- `frontier-scout packs sanction <server>` — **risk-gated**: a server with a dangerous
  flag (write / shell / credential / network) must show a safety summary /
  `--acknowledge-risk` first; low-risk servers sanction directly.
- `frontier-scout packs export --client claude-code --target ./out` — writes the
  **managed `allowedMcpServers` / `deniedMcpServers` fragment** (primary) + project
  `.mcp.json` (secondary) for an admin to deploy.
- `packs proof` (A/B/C proof variants) · `frontier-scout stats` (local opt-in funnel) ·
  `packs list / show / refresh / unsanction`.
- **Key modules:** `packs.py`, `pack_flow.py`, `safety_summary.py`,
  `exporters/claude_config.py`, `proof_variants.py`, `telemetry.py`; persistence in
  `store.py` (`pack_candidates`, `adoption_decisions`).

**Honesty invariants (load-bearing — keep copy *and* behavior aligned):** static
analysis only (the pack flow never runs a server); it **emits** config, it does **not
enforce** runtime policy; **Claude Code first** — Copilot / Cursor / Docker are roadmap,
not built; **research preview** — no PMF / adoption claim. The verdict schema
(`category`, `risk`, `fit`, `readiness`, `source_url`) stays aligned across the safety
summary, candidates `--json`, exporters, and tests.

## The agent adoption firewall (static, advisory — research preview)

A **second, static, advisory** surface beside the packs flow: `frontier-scout agent`. It helps a repo owner
adopt AI coding agents safely — scan repo risk surfaces, generate a conservative policy, pre-check a proposed
agent task, and keep an audit trail — **executing nothing**. Built this sprint; a research preview, not validated.

- `agent scan` — enumerate agent-risk surfaces (agent/MCP configs, CI, deploy, protected paths, secret-likely
  files **by name only — contents never read**) + detected test/lint/build checks. `--json` supported.
- `agent policy init | explain` — a conservative `frontier-scout.policy.json` (repo root; **JSON**; a distinct
  object from the radar's tool-adoption `.frontier-scout/policy.toml`).
- `agent check "<task>"` — evaluate a proposed task → `allow | needs_approval | block` (exit `0/3/4`). **Not
  named `trial`** — the radar's `trial`/`deps trial` *execute* a subprocess; `check` executes nothing.
- `agent receipts list | show` — JSON audit receipts under `<repo>/.frontier-scout/receipts/` (gitignored).
- `agent export claude | agents-md | pr-checklist` — advisory policy snippets (a format, not a client).
- **Key modules:** `agent_firewall/` (`models` · `scan` · `policy` · `decision` · `receipts`),
  `exporters/policy_snippets.py`; shared redaction `outputs/_text.scrub_secrets`; `doctor` gained
  agent-policy/receipts checks. Reuses `mcp_audit` (capability taxonomy), `safety_summary.RISKY_FLAGS`,
  `policy.PolicyFinding`, and the profiler's `_SKIP_DIRS` — no parallel taxonomy.

**Honesty invariants (load-bearing):** static only (no subprocess except a guarded read-only `git rev-parse`
for receipt metadata); secrets by name/path only; offline + keyless; **emit not enforce** (`block` is advisory
output, never a runtime kill-switch); the loader and decision engine **fail closed** (a missing/malformed
policy denies by default; every dangerous capability escalates to approval). Every persisted/emitted string is
redacted via `scrub_secrets`. See `docs/strategy/{repo-reality-check,security-review,autonomous-implementation-report}.md`.

## The engine underneath (the adoption radar)

`frontier-scout open` (or `--ui mission`) opens **Mission Control**
(`frontier_scout/tui3/`, Textual) — a dense, keyboard- **and** mouse-driven, 8-tab dashboard
(Scout · Schedule · Receipts · Guard · Packs · Deps · Reports · Settings). The radar
engine (`scout` · `evaluate` · `dossier` · `lab` · `trial` · `guard` · `policy` ·
`report`) ranks and audits tools/MCP servers; the packs product sits on top of it.

- A **bare `frontier-scout` prints help** (it no longer auto-launches the TUI — a
  stray invocation shouldn't drop you into a full-screen app). The TUI is launched
  explicitly via `open` / `--ui mission`.
- `--ui {mission,briefing,classic}` selects the UI (`mission` = tui3 when launched,
  `briefing` = tui2, `classic` = tui); `--demo` runs fully offline.
- Every renderable goes through `app._paint` (color↔mono) and `glyphs(unicode)`
  (unicode↔ASCII); layout reflows by breakpoint (`kit.breakpoint_for`). New
  widgets must route through these, or the fallbacks break.
- Lists that refresh use a single id-tagged `Static` repainted via `.update()`
  (never `remove_children()` + remount with the same ids → DuplicateIds).
- **Cell precision (load-bearing, v1.8.1):** glyph-art surfaces — the Adoption
  Matrix (a 59-cell box-grid), segmented gauges/`meter`, the scan `sweep`/spinner —
  are **width-parameterized pure functions** (`fn(width)->str`, `len(strip)==width`)
  that converge on `design_handoff_mission_control_v6/ascii_golden_frames.txt`.
  Measure display width with `kit.cell_width` (Rich `cell_len`), **never `len()`** —
  multi-cell ASCII glyphs (`(o)`=3 cells, `->`=2) drift otherwise. Build per-mode
  (`unicode=state.unicode`); never build-unicode-then-asciify (re-widens `(o)`).

## Experimental / parked

`incident` (**Incident Change Scout**, `frontier_scout/platform/incident_change_scout/`,
with fixtures under `examples/`, `prompts/`, and `evals/incident_change_scout/`) is a
**separate** incident-forensics vertical — a different problem/buyer — **parked during
the sanctioned-packs pivot** behind `FRONTIER_SCOUT_EXPERIMENTAL=1` (`cli.py`). The code
is kept, not deleted; it is **not** part of the packs product. Don't surface or extend it
as a headline feature.

## LLM backends (provider abstraction)

Needs **exactly one** backend; `--demo`/offline and the sanctioned-pack flow need none.
Pin with `--provider anthropic | openai | claude-cli | codex-cli`
(`frontier_scout/providers/`).

- Availability **deep-probes** `<cli> --version` (cached), so a broken-but-on-PATH
  CLI (e.g. a crashing `codex`) is treated unavailable, not silently selected (v1.8.1).
- The hermetic claude-CLI scout passes `--mcp-config '{"mcpServers": {}}'` (a bare
  `"{}"` is rejected by claude 2.x — "Invalid MCP configuration").

## Tests in this environment

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

- In the local conda setup use `/opt/miniconda3/bin/python` (bare `python` may not
  be on PATH). The 3 `tests/test_implement.py` failures are **env-only** (they shell
  out to `python`) — ignore them locally; they pass on CI.
- Some tui3 tests run the **real** demo scan, which is slow on a cluttered local tree
  (~10–15s), so they can time out locally yet pass on a clean CI checkout. Isolate a
  suspected regression by stashing and comparing against a clean tree first.
- **Convergence harness (v1.8.1):** the deterministic golden-frame + width tests
  (`test_tui3_golden_*`, `test_tui3_cells`, `test_tui3_bridging`) gate CI. The
  `pytest-textual-snapshot` SVG snapshots (`test_tui3_snapshots`) are a **local**
  tool — run with `-p pytest_textual_snapshot`; CI (autoload-off) skips them via
  `tests/conftest.py`, so they never break the merge gate.

## Packaging gotcha (load-bearing)

Non-`.py` data files (the Textual `theme.tcss` stylesheets) MUST be declared in
`pyproject.toml` `[tool.setuptools.package-data]` (`"*" = ["*.tcss"]`) + `MANIFEST.in`,
or `pip install` ships a wheel that **crashes on launch** (`StylesheetError`). Verify
a release against the **built wheel** (it bundles `tui3/theme.tcss` + `tui3/widgets.py`),
never the source tree. `release.yml` has a guard that fails the build if the wheel
lacks the stylesheets.

## Release process

1. Bump `version` in `pyproject.toml` + `frontier_scout/__init__.py`; add a
   `CHANGELOG.md` entry.
2. PR → CI `test` (full suite + `detect-secrets --all-files` secret scan + CodeQL).
   The secret scan flags keyword literals like `"credential"`/`"secrets": "..."`;
   mark genuine false positives with `# pragma: allowlist secret`.
3. `main` is protected (1 review + `enforce_admins` + conversation-resolution,
   **squash-only**): merge via the relax→merge→restore dance — PATCH
   `required_approving_review_count` 1→0, squash (`gh pr merge --squash --admin`),
   then →1 (**always restore**, even if the merge fails).
4. Tag `vX.Y.Z` → `release.yml` publishes the GitHub Release (draft→publish,
   immutable-safe) + PyPI (trusted publishing, gated by the `pypi` deployment
   environment — approve the pending deployment via `gh api ... pending_deployments`).
5. Verify the GitHub assets **and** the PyPI wheel bundle the `.tcss` stylesheets.
6. **Never reuse a burned version:** GitHub immutable-releases permanently reserve a
   deleted release's tag name (`v1.5.0` is dead) — bump to the next patch instead.

## Security / conventions

See `AGENTS.md` → "Conventions" and "Ask before changing". Load-bearing invariants: the
sanctioned-pack flow is **static only** (no MCP server is executed); exporters **emit**
config, they never **enforce**; repo source is never sent to an LLM (only filenames + AST
import names); fetched release text is data, not instructions; lab subprocesses stay
hermetic; nothing auto-installs; `evaluate`/`trial`/`guard`/`sanction` record evidence and
never grant repo/shell/network/credential permissions; don't read `.env.local` or upload
source for personalization.
