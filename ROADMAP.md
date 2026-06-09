# Roadmap

Public, local-first, and **demand-gated**. This repo is a **research preview**:
technically coherent, **not** market-validated. No PMF or adoption claim.

## Where we are — policy compiler + PR scope verifier (P0)

Frontier Scout compiles a typed repo policy into an AI coding agent's **native**
controls (Claude Code first), the agent emits **action receipts**, and CI verifies a
PR stayed within approved scope. Frontier Scout **emits** config and **verifies**
evidence — Claude Code and GitHub Actions do the enforcing. Keyless, offline, the only
runtime dependency is `pydantic`.

Shipped today (P0):

- `frontier-scout agent compile [--target claude] [--repo .] [--out .]` — compile
  `frontier-scout.policy.json` → `.claude/settings.json` (permissions), `.claude/hooks/`
  (decide allow/deny/ask + write receipts; a self-contained stdlib `_fs_guard.py`),
  `policy.lock.json`, a managed MCP allow/deny fragment, and a verify workflow.
- `frontier-scout agent verify-pr [--base <ref>] [--receipts <glob>] [--advisory]` — a
  fail-closed PR check (read-only `git diff` vs. receipts + lock) with GitHub annotations.
- `frontier-scout agent scan | policy init|explain | check | receipts` — static repo
  scan, policy authoring, a static task pre-check, and receipt inspection.
- `frontier-scout doctor` — offline agent-readiness check.

## Next (P1) — build only on validated pull

The next milestone is **design-partner validation**: real PRs gated by `verify-pr` on a
real repo (target: one design-partner repo on real PRs within 90 days). Then, gated by
that pull:

- **Codex adapter** — compile the same policy to Codex managed `requirements.toml` +
  hooks; CI verifier already covers the diff side.
- **Optional receipt/provenance integration** — export local action records to existing
  receipt/provenance systems (for example, Agent Receipts or GitHub artifact attestations /
  Sigstore). Frontier Scout does not build its own signed-receipt protocol, SDK, daemon, or
  ledger.
- **Scanner findings as policy inputs** — seed protected paths/risk from CodeQL /
  Dependabot / Semgrep output.

## Later (P2)

- Passive adapters for **Cursor** and **GitHub Copilot coding agent**.
- **Gateway-import mode** for orgs already running Cloudflare/MintMCP-class MCP gateways.

## Non-goals (explicitly not built)

A new agent runtime, a sandbox, a general MCP gateway, a custom policy language, a custom
telemetry format, a signed ledger, a static adoption radar, or a Mission Control UI — the
ecosystem already provides these and Frontier Scout compiles to / verifies them. Also: no
hosted SaaS as the default, no auto-install into a user's repo, and no replacing human
review — `verify-pr` produces **control evidence, not a guarantee**.
