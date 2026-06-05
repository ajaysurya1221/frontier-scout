> [!NOTE]
> **Research preview — intended to merge to correct the public repo identity** (per `traction_research/research_3.pdf`).
> Public `main` still tells the old radar / guard / receipt story; merging this makes the honest
> sanctioned-packs preview the default branch. **This is not a release:** do **not** tag, publish to PyPI,
> or cut a GitHub release from this PR. It is **not market validation, not PMF, not demand proof** — the
> human design-partner gate is still **0/5**.
>
> - **Claude Code managed-config export first today.** Copilot / Cursor / Docker / GitHub allow-list are **roadmap** unless separately implemented.
> - **Static analysis only** — **no MCP server is behaviorally executed** in the sanctioned-pack flow.
> - Frontier Scout **emits config fragments for admin/developer review; it does not enforce runtime policy.**

## What changed
Frontier Scout pivots from a broad "AI adoption radar" to **repo-aware sanctioned MCP-server packs for
Claude Code**: rank approved MCP servers against your repo → read a **static** capability + policy safety
map per server → risk-gate the sanction decision → **export the approved set into Claude Code's managed
config** (`allowedMcpServers` / `deniedMcpServers`) + a project `.mcp.json`. Keyless, offline. The old
radar remains as the ranking/safety engine underneath, not the headline.

## Why the pivot exists
Two research passes (`research_2.pdf`, `research_3.pdf`) found the market converging on install-time
allowlists, managed configs, and curated catalogs, with the big clients owning enforcement/runtime. The
one defensible seam is a **repo-aware curation + translation overlay into existing control planes**
(Claude/GitHub/Docker/ToolHive) — not replacing them. `research_3` adds: the branch is already honest, but
**public `main` still tells the old story**, so the next move is *public-identity correction* — merge this
PR (no release). See `docs/pivot/RESEARCH_3_EXECUTION_DECISION.md`.

## What is intentionally NOT built
- ❌ Behavioral MCP sandbox/trial execution (no server is run).
- ❌ Copilot / Cursor / Docker / GitHub allow-list / cross-client exporters (roadmap; the CLI **hard-errors** on non-Claude clients).
- ❌ Blocking CI guard (the guard is non-blocking / notifier only).
- ❌ Runtime enforcement, registry ownership, governance control plane, hosted service.

## Exact claim boundaries
- **Claude Code managed-config export first today.** Copilot/Cursor/Docker/GitHub allow-list are roadmap unless separately implemented.
- **Static analysis only** — no MCP server is behaviorally executed in the sanctioned-pack flow.
- Frontier Scout **emits** config fragments; an admin deploys them; **it does not enforce** runtime policy.
- The Tech-Radar `trial` verdict ring is shown as **`review`** in packs output (data tier preserved); nothing implies execution.

## Gold-path example (CLI-generated, not hand-written)
`docs/examples/sanctioned-packs/` — candidates → static safety summary → Claude managed-config fragment +
project `.mcp.json`, all produced by the real CLI offline. Static only; no server executed; no
copilot/cursor/docker config; no secrets.

## Test evidence
- Full non-live suite: **669 passed / 0 failed** (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 … pytest -m "not live" -q`).
- The 3 previously env-only `test_implement.py` cases were made portable (`sys.executable`) — 0 env-only failures remain.
- CodeRabbit review addressed in `0a3e2e4` (exporter credential-strip + fail-closed registry + `--json` paths + telemetry robustness), with `tests/test_review_hardening.py`.
- `ruff check` + `ruff format --check` clean on changed source.

## Built-wheel smoke evidence
- `python -m build` → `dist/frontier_scout-1.8.1-py3-none-any.whl`; wheel bundles `tui2`/`tui3`
  `theme.tcss` + `tui3/widgets.py` (StylesheetError-on-launch gotcha covered; a headless Textual boot
  resolved the stylesheet).
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
(`docs/pivot/SYNTHETIC_VALIDATION_REPORT.md`). Passive OSS feedback (the issue forms +
`docs/pivot/PASSIVE_SIGNAL_LEDGER.md`) is weak signal only and does not move the gate.

## Next decision rule
- **Merge** corrects the public identity (research_3). **Do not** release/tag/publish from this PR.
- **Build V1** (behavioral sandbox, cross-client export, CI guard) **only after** real workflow-shaped pull:
  one external user routing the Claude export through a real process, or two independently asking for the
  same downstream target. Otherwise keep collecting weak signal.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
