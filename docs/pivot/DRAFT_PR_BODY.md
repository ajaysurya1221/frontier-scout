> [!WARNING]
> **DRAFT — DO NOT MERGE until explicitly authorized.** This is a **research preview**, not a release.
> It is **not market validation, not PMF, not demand proof**, and carries **no human-validation claim**.
>
> - **Claude Code managed-config export first today.** Copilot / Cursor / Docker are **roadmap** unless separately implemented.
> - The sanctioned-pack safety output is **static analysis only** — **no MCP server is behaviorally executed** in the sanctioned-pack flow.
> - Frontier Scout **emits config fragments; it does not enforce runtime policy.**

## What changed
Frontier Scout pivots from a broad "AI adoption radar" to **repo-aware sanctioned MCP-server packs for
Claude Code**: rank approved MCP servers against your repo → read a **static** capability + policy safety
map per server → risk-gate the sanction decision → **export the approved set into Claude Code's managed
config** (`allowedMcpServers` / `deniedMcpServers`) + a project `.mcp.json`. Keyless, offline. The old
radar remains as the ranking/safety engine underneath, not the headline.

## Why the pivot exists
A follow-up pre-mortem (`research_2.pdf`) found the market converging on install-time allowlists, managed
configs, and curated catalogs — and that a downstream CI-guard/receipt wedge would be routed around. The
defensible seam is **repo-aware prioritization + a config fragment that coexists with** (does not
out-govern) Claude/GitHub/Docker. See `docs/pivot/REVISED_IMPLEMENTATION_PLAN.md`.

## What is intentionally NOT built
- ❌ Behavioral MCP sandbox/trial execution (no server is run).
- ❌ Copilot / Cursor / Docker / GitHub allow-list / cross-client exporters (roadmap; the CLI **hard-errors** on non-Claude clients).
- ❌ Blocking CI guard (the guard is non-blocking / notifier only).
- ❌ Runtime enforcement, registry ownership, governance control plane.

## Exact claim boundaries
- **Claude Code managed-config export first today.** Copilot/Cursor/Docker are roadmap unless separately implemented.
- **Static analysis only** — no MCP server is behaviorally executed in the sanctioned-pack flow.
- Frontier Scout **emits** config fragments; an admin deploys them; **it does not enforce** runtime policy.
- The Tech-Radar `trial` verdict ring is shown as **`review`** in packs output (data tier preserved); nothing implies execution.

## Test evidence
- Full non-live suite: **663 passed / 0 failed** (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 … pytest -m "not live" -q`).
- The 3 previously env-only `test_implement.py` cases were made portable (`sys.executable`) — 0 env-only failures remain.
- `ruff check` + `ruff format --check` clean on changed source.

## Built-wheel smoke evidence
- `python -m build` → `dist/frontier_scout-1.8.1-py3-none-any.whl`; wheel bundles `tui2`/`tui3`
  `theme.tcss` + `tui3/widgets.py` (the StylesheetError-on-launch gotcha is covered; a headless Textual
  boot resolved the stylesheet).
- Clean-venv install + **offline e2e**: candidates → static review → sanction → export; JSON shapes match
  fixtures; repo unchanged; copilot/cursor gated (rc=2, no output); no secrets; no network egress.

## Remaining residuals (documented, not bugs)
- Tech-Radar `trial`/`receipt`/`sandbox` vocabulary survives in the **radar/lab/deps** product (out of
  packs scope; the lab genuinely executes, so its terms are true).
- `formal_receipt` proof-variant key kept (content is `STATIC ADOPTION ASSESSMENT` / `generated-by`).
- `scripts/` + `outputs/` ship as top-level packages (required by the live scan import) — a future cleanup.

## Validation status
**0 / 5 real human design-partner sessions.** This PR is **technically coherent and claim-honest — it is
not market validation, PMF, or adoption proof.** Synthetic/agent reviews informed it but do not count
(`docs/pivot/SYNTHETIC_VALIDATION_REPORT.md`). Passive OSS feedback (the new issue forms +
`docs/pivot/PASSIVE_SIGNAL_LEDGER.md`) is weak signal only and does not move the gate.

## Next decision rule
- **Build V1** (behavioral sandbox, cross-client export, CI guard) **only after** external pull or human
  validation appears (a GO from `docs/pivot/HUMAN_VALIDATION_SCRIPT.md` → `VALIDATION_LEDGER.md`).
- **Otherwise** keep as a research preview / local artifact. Do not merge/tag/release/publish on the
  strength of internal rigor alone.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
