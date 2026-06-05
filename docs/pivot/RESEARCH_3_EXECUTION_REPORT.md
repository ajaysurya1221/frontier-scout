# Research_3 Execution Report (pre-merge)

**Date:** 2026-06-05 · **Branch:** `pivot/sanctioned-packs` · **PR:** #43 · **Sprint:** *pivot: public research-preview identity correction*

## 1. Research_3 decision (summary)
Continue Frontier Scout **only as a research preview** on one narrow job — repo-aware sanctioned MCP-pack
recommendation + static safety summary + admin-deployable Claude Code managed-config fragment (a
curation/translation overlay into existing control planes, never owning runtime/enforcement). The
strongest surviving seam is repo-aware curation + translation. The default branch (`main`) still tells the
old radar/receipt/CI-guard story, so the next move is **public-identity correction**: make the honest
preview the default public identity by **merging PR #43 → `main`**, with **no release/tag/publish** and
**no V1 features**.

## 2. Files changed (this sprint)
- `README.md` — demote the radar from the public identity: replaced the Mission Control screenshot with the real `packs candidates → export` flow; reframed the "60-second demo" as the legacy radar **engine**; rewrote the Roadmap to lead with the sanctioned-packs research preview and collapse the radar history (removed the stale "Mission Control v5 *(in progress)*").
- `docs/pivot/RESEARCH_3_EXECUTION_DECISION.md` *(new)* — verdict, allowed next move, do-not-build list, evidence ladder, "this is not market validation."
- `docs/examples/sanctioned-packs/` *(new)* — gold-path example (README + CLI-generated `example-candidates.json`, `example-static-safety-summary.md`, `example-claude-managed-config.json`, `example-project-mcp.json`).
- `.github/ISSUE_TEMPLATE/sanctioned-pack-feedback.yml` — control-plane intake question (Claude managed settings / GitHub MCP allow-list / Docker / ToolHive / Copilot / Cursor / Other) + "which one export target matters most."
- `docs/pivot/DRAFT_PR_BODY.md` — reframed from "DO NOT MERGE" to "merge to correct public identity; no release."
- `docs/pivot/RESEARCH_3_EXECUTION_REPORT.md` *(this file)*.

## 3. Source code changed?
**No.** Docs / examples / issue-template only (`git status` shows no `frontier_scout/**.py`). The non-live
suite remains **669/0** at the last source commit (`0a3e2e4`); not re-run because no source changed.

## 4. Docs / examples added or updated
Decision doc, gold-path example set (5 files, CLI-generated + verified), PR body, README identity, this report.

## 5. Feedback scaffolding added or verified
Verified present + updated: `sanctioned-pack-feedback.yml` (control-plane question), `client-export-request.yml`,
`docs/pivot/PASSIVE_SIGNAL_LEDGER.md` ("passive OSS feedback is not the 5 real sessions"). All frame OSS
input as **weak signal**, not validation.

## 6. Claim-boundary audit
Four review subagents (research_3 compliance / public identity / claim-honesty / merge safety). Results:
**compliance ✅**, **claim-honesty ✅ clean** (no user-facing string implies runtime enforcement,
behavioral sandbox in the pack flow, native Copilot/Cursor/Docker, market validation, design-partner
completion, or PMF), **public identity** — the README radar-foregrounding flagged by the auditor was
**fixed** (items in §2). Risky terms (`trial`/`sandbox`/`receipt`/`guard`) that remain are confined to the
radar/lab/deps surfaces, which genuinely execute, so they are technically true and out of the packs scope.

## 7. Verification
`git status` (docs-only); feedback YAML parses (9 fields); all example JSON parses + matches managed/project
shapes; no secrets / no Copilot/Cursor/Docker config in the export; CLI smoke (`--help`, `packs --help`,
`packs candidates --help`, `packs export --help`) all OK. CI on the PR head is green (`test` + CodeQL +
Analyze pass).

## 8. PR #43 state
Title **"pivot: sanctioned MCP packs research preview"**, base `main`, CI green, converted **Draft → Ready**,
body updated, `do-not-merge` label removed (merge now authorized), `research-preview` + `needs-feedback` kept.

## 9. Was PR #43 merged?
**No — blocked (verdict B).** `main` protection requires **1 approving review + `enforce_admins`**; the PR
author is the repo owner (GitHub blocks self-approval) and the sprint's hard constraints forbid editing
branch protection / force-push / bypass. A constraint-compliant merge therefore needs a **second collaborator's
approving review** (then a squash merge), or the **maintainer** to relax protection themselves. No bypass was
performed.

## 10. Commit hash merged
N/A (not merged).

## 11. **This work corrects public identity and research-preview readiness. It is not market validation.**

## 12. **No behavioral MCP sandbox, cross-client export, blocking CI guard, hosted product, tag, release, or publish was performed.**

## 13. Recommended next step
After the merge clears (maintainer approval), **collect weak external signal only** in the narrowest channels
(Claude Code / MCP communities, GitHub Discussions, a short demo clip). **Do not build V1** (behavioral probe,
cross-client export, CI guard) until a real workflow-shaped pull appears — one external user routing the Claude
export through a real process, or two independently requesting the same downstream target.
