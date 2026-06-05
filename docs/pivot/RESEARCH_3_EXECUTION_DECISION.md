# Research_3 Execution Decision

**Date:** 2026-06-05 · **Branch:** `pivot/sanctioned-packs` · **PR:** #43 · **Source:** `traction_research/research_3.pdf`

## Research_3 verdict (one paragraph)
Frontier Scout should continue, but **only as a research-preview product centered on one narrow job**:
repo-aware sanctioned MCP-pack recommendation + a static safety summary + an admin-deployable Claude Code
managed-config fragment. It should **not** become a broad AI-tool radar again, **not** a runtime sandbox /
enforcement plane, and **not** expand into generic cross-client export. The strongest surviving seam is a
**curation-and-prioritization overlay that fits into existing control planes** (Anthropic managed config,
GitHub registry/allow-list, Docker catalogs, ToolHive) rather than replacing them — because the registries
are deliberately unopinionated, the big clients own enforcement/runtime, and raw discovery is becoming a
commodity while curation / ranking / decision-support remain open. The repo's real problem is
**public-identity coherence**, not technical coherence: the default branch (`main`) still markets the old
radar / guard / receipt story while the branch tells the honest one.

## Allowed next move
**Identity correction, not new product scope.** Make the honest sanctioned-packs research preview the
**default public repo identity** before any wider distribution — by merging PR #43 into `main` (research_3's
explicit recommendation), **with no release, tag, or PyPI publish**. Add one gold-path example
(`docs/examples/sanctioned-packs/`) and one high-signal intake mechanism (a feedback template asking which
**control plane** the user is on today). Then collect weak external signal only.

## Do-not-build list (short, strict)
- Behavioral MCP probe / sandbox runtime.
- Generic cross-client export (Copilot / Cursor / Docker / GitHub allow-list).
- Blocking CI guard.
- Hosted service / accounts / billing / cloud telemetry.
- TUI as the core differentiator.
- Revived broad "AI-tool radar" / GitHub-Action / CI-guard / receipt-first positioning.

## Evidence ladder (do not collapse the rungs)
| Signal | Confidence | Justifies | Does NOT justify |
|---|---|---|---|
| Technical (suite / wheel / fixtures green) | high (correctness) | sharing as a research preview | claiming demand |
| Claim-honesty (audits, copy-hardening, spec vs Anthropic/GitHub/Docker docs) | high (truthfulness) | saying what it is / isn't | claiming PMF |
| Ecosystem (this memo) | med-high (strategy) | picking a wedge, saying no to adjacent features | claiming users want this implementation |
| Passive OSS (stars / forks / comments) | low | deciding whether messaging is legible | deciding to build V1 |
| Active OSS (a real "how do I use this with X" issue) | medium | one small next step if repeated | broad roadmap expansion |
| Real validation (someone routes the artifact through a real control plane) | high | the narrow Claude-admin-bundle next step | the full company thesis |
| Repeat use | very high | building V1 around that seam | — |

Current external signal: **0 stars, 0 forks, 1 open PR; human design-partner gate 0/5.** Enough to continue
a research preview; nowhere near enough to build a heavier product.

## Decision
- **Continue as a research preview** on the one narrow job.
- **Make the public default repo identity truthful** — merge PR #43 → `main` so `main` stops telling the
  old radar / guard / receipt story. (Gated on the merge conditions in `RESEARCH_3_EXECUTION_REPORT.md`;
  this repo's `main` requires an approving review + `enforce_admins`, so the final merge click is the
  maintainer's.)
- **No release / tag / PyPI publish. No V1 features.**
- **No market-validation claim. This is not market validation.**
- Next step after identity correction: collect weak external signal in the narrowest channels; build V1
  **only** if a real workflow-shaped pull appears (one external user routing the Claude export, or two
  independently asking for the same downstream target).
