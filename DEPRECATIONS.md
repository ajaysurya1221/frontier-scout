# Deprecations & repositioning notices

Frontier Scout is repositioning from a broad "AI-adoption radar" into a focused
**sanctioned MCP-server packs** product for coding assistants (see
`docs/pivot/REVISED_IMPLEMENTATION_PLAN.md`). Nothing below is deleted yet — these are
*notices* so the change is reversible and compatibility is preserved.

## Parked (kept, de-emphasized — not removed)

- **Incident Change Scout** (`frontier_scout/platform/incident_change_scout/*`, the `incident`
  CLI subcommand). A distinct second problem (different trigger/workflow/buyer). Both research
  passes agree it should leave the opening narrative. It is moving **behind an experimental flag**
  (`FRONTIER_SCOUT_EXPERIMENTAL=1`); the code stays. Revisit only after a live control plane +
  real usage data.

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
