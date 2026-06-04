# Validation protocol — 2-week design-partner test

The follow-up research (`traction_research/research_2.pdf`) is explicit: **do not spend the next
two weeks polishing an artifact — spend them proving teams want a sanctioned fast path at
install/runtime.** This protocol operationalizes that. It is the Phase-3 gate: its result decides
whether to keep building (Phase 4 / V1) or re-scope.

## Who

5 design partners, each a **platform-engineering or AppSec lead** at a GitHub-heavy org whose
developers use **Claude Code** (and/or Copilot). Avoid solo devs and tiny startups (weak fits).

## The artifact under test

The MVP, run keyless and offline:

```bash
frontier-scout packs candidates --repo . --client claude-code      # repo-ranked sanctioned pack
frontier-scout packs sanction <server> --repo . [--acknowledge-risk]  # risk-gated approval
frontier-scout packs export  --client claude-code --target ./out   # managed-config + .mcp.json
```

## Baseline to capture first (per partner)

Before showing the tool, record the **current-state cost**: "How do you decide and roll out a new
MCP server for your team today, and how long does it take?" (Slack thread, wiki page, hand-edited
`.mcp.json`, security review.) This is the bar the export must beat — capture minutes/steps.

## The three validation steps (from the research)

1. **Pack pull.** Let the partner run `packs candidates` on a real repo and review the repo-ranked
   list. **Success metric: ≥3 of 5 say they would rather use this than hand-curate `.mcp.json` or
   Slack/wiki guidance.**
2. **Proof variant (A/B/C).** Show the same server three ways — `approval_only`,
   `sandbox_summary`, `formal_receipt` (`frontier_scout/proof_variants.py`). Ask which they would
   *keep*. **Success metric: users voluntarily ask to keep one** (the research predicts the
   sandbox summary wins; if they resist explicit receipts, kill "receipts" as a headline). Record
   the choice (`record_preference(...)`, opt-in telemetry).
3. **Export snap-in.** Have them take the exported `managed-settings.json` / `.mcp.json` toward
   their real control plane. **Success metric: ≥1 team says "we could actually route this through
   our current process."** If none do, the output format is wrong even if the analysis is good.

## Instrumentation

Turn on local, opt-in telemetry (`FRONTIER_SCOUT_TELEMETRY=1`) during sessions and read the funnel
with `frontier-scout stats`: `candidates_viewed → sanctioned/blocked → exported → proof_variant_kept`.
Partners export their own `pack-events.jsonl` and share it — nothing phones home.

## Decision gate (go / re-scope)

**GO (keep building → Phase 4 / V1):** ≥3/5 pack-pull preference **and** ≥1 export snap-in.
Then build the demand-justified surfaces: the behavioral MCP probe (high-risk servers only — see
`docs/spike-mcp-probe.md`), a second client (Copilot) + GitHub allow-list exporter, and the
non-blocking policy-drift notifier.

**Kill criteria (re-scope, do NOT keep polishing):**
- **< 3/5** prefer the pack to hand-curation → the curation+repo-fit seam isn't pulling; re-scope
  to the narrowest sub-problem that earns repeated operational pull.
- **No team** will route the export through their process → the artifact/integration is wrong;
  fix the export target (or pivot to feeding Docker/ToolHive catalogs) before anything else.
- Partners say "we just need better policy data, not a product" → become middleware, not a surface.

## What this protocol deliberately does NOT do

It does not build the behavioral sandbox probe, the GitHub Action, the Backstage feed, or a hard
CI guard first. Those are gated on the result above.
