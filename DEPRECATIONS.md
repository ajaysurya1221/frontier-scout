# Deprecations & removals

## 2.0.0 — pivot to policy compiler + PR receipt verifier

Frontier Scout is now a **policy compiler + PR receipt verifier** for AI coding agents
(Claude Code first). The product surface narrowed to one wedge, and the off-strategy
surfaces were **removed** (not just parked) so the repo matches the product.

### Removed CLI / surfaces

| Removed | Replacement / rationale |
|---|---|
| `scan` · `evaluate` · `dossier` · `lab` · `trial` · `guard` · `report` (the adoption radar) | Off-strategy: the product governs agents, it doesn't discover/rank tools. |
| `packs …` (sanctioned MCP-server packs) | The MCP dimension is now a policy field (`mcp_server_allowlist`) compiled into native allow/deny. |
| `open` · `setup` · `--ui` (Mission Control TUI + wizard) | The buyer lives in PRs/CI, not a local TUI. |
| `cron` · `stats` · `notifications` · `deps` · `implement` · `profile` · `clear-history` | Off-strategy; scheduling belongs to GitHub Actions. |
| `--provider` / LLM backends | The compiler/verifier is deterministic, keyless, and offline. |

### Removed modules

`platform/` (a home-grown runtime/gateway/authz substrate), `providers/`, `scripts/` (LLM
tooling), `store.py` (SQLite), `tui3/`, `wizard/`, and the radar/packs modules. `policy.py`
and `safety_summary.py` were trimmed to their shared cores (`PolicyFinding`/`Severity` and
`RISKY_FLAGS`), still reused by the agent-firewall decision engine.

### Changed

- `agent export claude` → use **`agent compile`** for enforceable native config (settings +
  hooks + CI verifier). The advisory markdown snippet still ships; `agent export
  agents-md|pr-checklist` are unchanged advisory aids.
- `doctor` is now a minimal, offline agent-readiness check.

### Pending docs cleanup

Several `docs/` files (ADRs for the SQLite/graph/vector/gateway/authz substrate, the
architecture/reference-stack write-ups) still describe removed surfaces and will be pruned
or superseded in a follow-up. `docs/spike-claude-config.md` is kept — it pins the native
config shapes the compiler emits.
