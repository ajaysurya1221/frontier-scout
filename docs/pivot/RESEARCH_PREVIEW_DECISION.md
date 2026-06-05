# Research-Preview Decision

**Date:** 2026-06-05 · **Branch:** `pivot/sanctioned-packs`

## Verdict
**Research preview candidate — technically coherent, not market validated.** Frontier Scout's
sanctioned-MCP-packs flow is a claim-honest, technically coherent, research-driven product artifact and
local preview. It is **not** market validation, **not** PMF, **not** demand proof.

## Evidence
- **Tested commit:** `4418949` (on top of `b8cafdb` claim-honesty hardening).
- **Prior gate:** [`INTERNAL_RIGOR_GATE_REPORT.md`](INTERNAL_RIGOR_GATE_REPORT.md) — PASS WITH RESIDUALS.
- **Claim-honesty status:** [`CLAIM_HONESTY_HARDENING_REPORT.md`](CLAIM_HONESTY_HARDENING_REPORT.md) —
  Claude-Code-only (copilot/cursor hard-error); static-only language (no "trial"/sandbox/receipt
  overclaim; the Tech-Radar `trial` ring renders as `review` in packs output); export framed as an
  emitted fragment, not enforcement.
- **Test status:** **663 passed / 0 failed** (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 … pytest -m "not live" -q`).
- **Built wheel (from the gate):** `dist/frontier_scout-1.8.1-py3-none-any.whl` — bundles the
  `tui2`/`tui3` `theme.tcss` + `tui3/widgets.py`; clean-venv install + offline e2e verified (a local
  preview build of the working tree; **no version bump / no release**).

## Explicit non-goals (this preview)
- **No behavioral sandbox** — no MCP server is started or executed in the sanctioned-pack flow.
- **No cross-client export** — Copilot / Cursor / Docker / GitHub allow-list exporters are roadmap, not built.
- **No blocking CI guard** — the guard is non-blocking (notifier only).
- **No runtime enforcement** — Frontier Scout emits config fragments; an admin deploys them; FS does not enforce.
- **No human-validation claim** — synthetic/agent feedback is not market validation.

## Remaining uncertainty (only real users can resolve)
1. Whether real users prefer this to hand-curating `.mcp.json` (or a Slack thread / wiki).
2. Whether a real team would route the Claude managed-config fragment through Jamf / Intune / admin deployment.
3. Whether the **static** safety output is enough, or whether **behavioral** evidence is required to sanction high-risk servers.

## Decision
**Proceed as a research preview / local preview artifact. Do not build V1 features (behavioral sandbox,
cross-client export, blocking CI guard) until external pull or human validation appears.** The real
go/no-go remains the 5 design-partner sessions in
[`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md) → [`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md)
(currently **0/5**). Passive OSS feedback (see [`PASSIVE_SIGNAL_LEDGER.md`](PASSIVE_SIGNAL_LEDGER.md)) may
inform prioritization but does **not** count toward that gate.
