# Deprecations & repositioning notices

Frontier Scout is repositioning from a broad "AI-adoption radar" into a focused
**sanctioned MCP-server packs** product for coding assistants. Nothing below is deleted yet — these are
*notices* so the change is reversible and compatibility is preserved.

## Naming — two distinct "Adoption Firewall" concepts (disambiguated)

The legacy radar slice (`evaluate` / `trial` / `guard` / `policy`) historically carried the label
"Adoption Firewall" (e.g. the `policy` command help). The new **static agent adoption firewall** ships
under a separate, collision-free **`frontier-scout agent`** command group (`agent scan` / `policy` /
`check` / `receipts` / `export`) with a distinct policy object (`frontier-scout.policy.json`, JSON) and
distinct receipts (`<repo>/.frontier-scout/receipts/`). The two do **not** share state or schema:

- **Legacy radar `policy` / `trial` / `guard`** — tool-*adoption* tuning (TOML `.frontier-scout/policy.toml`,
  verdicts `adopt/trial/assess/hold`). `trial` and `deps trial` **execute** a sandboxed subprocess. Kept,
  untouched, de-emphasized.
- **New `agent` group** — task-*authorization* pre-checks (JSON policy, verdicts `allow/needs_approval/block`).
  **Executes nothing**; advisory only. This is the product surface going forward for agent governance.

The new `agent check` is deliberately **not** named `trial` to avoid implying execution.

## Parked (kept, de-emphasized — not removed)

- **The hard, blocking CI `guard`** as a *product surface*. The follow-up research finds a
  gate-with-no-sanctioned-path reads as friction, not relief. `frontier_scout/guard.py` remains
  (CI-friendly, read-only), but the product direction is a **non-blocking** "unsanctioned tool /
  policy drift detected" notifier (V1). No behavior removed.

- **The "AI-adoption radar" headline framing** and **"bring your own LLM"** as a top-level
  differentiator. Demoted in copy (README / CLI help / wizard). The radar feed, providers, scan,
  and TUI all still work — they are now *the ranking engine behind the product*, not the pitch.

- **Dependency-triage as a co-headline** (`deps`). Kept as a capability; not a headline (the
  follow-up research ranks repo-aware dep triage as narrower and more crowded).

## Superseded planning artifacts

- The prior `intake <url>` gate + `intake_decisions` v7 table design (never built) is superseded
  by the pack-centric flow (`packs candidates/sanction/export`).
- The prior **Backstage** exporter "later bet" is replaced by Claude/GitHub/Docker control-plane
  exporters (the follow-up research's named integration targets).

## Compatibility commitments

- No existing CLI subcommand is removed in this pivot. New verbs are additive.
- The SQLite schema change (`"sanctioned"` pack-candidate state) is an additive, idempotent,
  data-preserving table-rebuild migration; existing rows are retained.
- The offline `demo` path and all local-first / no-telemetry invariants are preserved.
