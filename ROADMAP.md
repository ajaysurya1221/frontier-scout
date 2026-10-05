# Roadmap

Public, local-first, and **demand-gated**. This repo is a **research preview**:
technically coherent, **not** market-validated. No PMF or adoption claim.

## Where we are — policy compiler + PR scope verifier (P0)

Frontier Scout compiles a typed repo policy into an AI coding agent's **native**
controls (Claude Code first), the agent emits **action receipts**, and CI checks a
PR's diff against the scope declared by the base commit's policy. Receipts are unsigned
observations and never count as approval. Frontier Scout **emits** config and **checks**
evidence — Claude Code and GitHub Actions do the enforcing. Keyless, offline, the only
runtime dependency is `pydantic`.

Shipped today (P0):

- `frontier-scout agent compile [--target claude] [--repo .] [--out .]` — compile
  `frontier-scout.policy.json` → `.claude/settings.json` (permissions), `.claude/hooks/`
  (decide allow/deny/ask + write receipts; a self-contained stdlib `_fs_guard.py`),
  `policy.lock.json`, a managed MCP allow/deny fragment, and a verify workflow.
- `frontier-scout agent verify-pr [--base <ref>] [--receipts <glob>] [--advisory]` — a PR
  scope check (read-only `git diff --name-status -z -M` against the base commit's policy
  and lock) with reason-coded GitHub annotations. FAIL or UNVERIFIED is never reported as
  PASS. The 2026-10-06 repair of five false acceptance paths is unreleased; see
  [docs/evaluation/verifier-2026-10-06.md](docs/evaluation/verifier-2026-10-06.md).
- `frontier-scout agent scan | policy init|explain | check | receipts` — static repo
  scan, policy authoring, a static task pre-check, and receipt inspection.
- `frontier-scout doctor` — offline agent-readiness check.

## Next (P1) — build only on validated pull

The gate for this milestone was **design-partner validation**: real PRs gated by
`verify-pr` on real repos, pre-registered publicly in [KILL_CRITERIA.md](KILL_CRITERIA.md)
(3 unaffiliated orgs · ≥20 agent PRs/week · 4-week retention · ≥1 unprompted payment
signal, by day 90). Those gates were **not met** at the
[day-90 evaluation](KILL_CRITERIA.md#day-90-evaluation-2026-09-30), so the items below
are not commitments — they get built only if someone with a real use case asks:

- **Codex adapter** — compile the same policy to Codex managed `requirements.toml` +
  hooks; CI verifier already covers the diff side.
- **Optional receipt/provenance integration** — export local action records to existing
  receipt/provenance systems (for example, Agent Receipts or GitHub artifact attestations /
  Sigstore). Frontier Scout does not build its own signed-receipt protocol, SDK, daemon, or
  ledger.
- **Scanner findings as policy inputs** — seed protected paths/risk from CodeQL /
  Dependabot / Semgrep output.
- **Authenticated approval provenance (deferred)** — today a protected-path change is never
  green, because unsigned receipts cannot show who approved it. Making it green needs an
  approval record outside the agent's control, for example a verified GitHub review or an
  attestation by an approver identity, not a receipt format of our own.

## Later (P2)

- Passive adapters for **Cursor** and **GitHub Copilot coding agent**.
- **Gateway-import mode** for orgs already running Cloudflare/MintMCP-class MCP gateways.

## Non-goals (explicitly not built)

A new agent runtime, a sandbox, a general MCP gateway, a custom policy language, a custom
telemetry format, a signed ledger, a static adoption radar, or a Mission Control UI — the
ecosystem already provides these and Frontier Scout compiles to / verifies them. Also: no
hosted SaaS as the default, no auto-install into a user's repo, and no replacing human
review — `verify-pr` produces **control evidence, not a guarantee**.
