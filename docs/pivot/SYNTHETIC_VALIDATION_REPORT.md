# Synthetic Validation Report — Sanctioned MCP Packs

> ⚠️ **SYNTHETIC — NOT REAL MARKET VALIDATION.** Every verdict, persona, and preference below was
> produced by AI subagents in a rehearsal sprint. **No external human gave feedback.** Per this
> project's own rule, *agent feedback is not demand evidence* and cannot move the GO/KILL gate.
> The real gate in [`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md) is still **0 / 5** and can only be
> filled by 5 real external humans running [`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md).
>
> **What this sprint is *for*:** (1) catch research-drift before sessions; (2) find demo-clarity bugs
> that would waste real sessions; (3) map the objections to rehearse against; (4) stress the wedge
> against incumbents. **What it is *not*:** proof anyone wants this.

**Date:** 2026-06-05 · **Method:** 9 independent subagents (1 research gatekeeper · 1 demo critic ·
5 isolated skeptical personas · 1 competitor red team · 1 outreach operator). Personas were dispatched
*separately* (no shared context) so they couldn't anchor on each other.

---

## 1. Headline (synthetic)

| Signal | Synthetic result | How to read it |
|---|---|---|
| Panel verdict | **0 GO · 3 MODIFY · 2 KILL** | NOT a kill signal — see §2. The clustering is the signal, not the count. |
| Dominant objection | **"static ≠ behavioral"** (5/5 personas) | This is the *research's own deferred-V1 hypothesis* — the thing real sessions exist to test. Do **not** resolve it from synthetic feedback. |
| Demo bugs found | **2 trust-detonating CLI overclaims** | The actionable find. Fixable copy. Confounds sessions if left. See §4. |
| Research compliance | **3/4 PASS, 1 minor DRIFT** | Plan still faithful to `research_2.pdf`. See §3. |
| Strategic threat | **Anthropic owns the export surface** | Real, but a positioning constraint, not a build. See §6. |

**Why "2 KILL" is not a kill:** both KILLs (DevTools lead, skeptical CTO) reduce to *"feature not a
company / an incumbent absorbs this"* — the **competitor red team's** thesis, not new demand data. A
simulated skeptic cannot KILL a thesis; only the absence of real pull can. Treating the synthetic KILL
as decisive would be the exact error this project forbade.

---

## 2. The trap this sprint set (and why we're not falling in it)

Every persona's loudest demand was **"ship the behavioral sandbox."** It is tempting — it's the obvious
gap, and 5/5 "asked" for it. **We are not building it**, because:

1. **Hard rule #1** forbids it.
2. It is precisely *"agent feedback treated as validation"* — which you forbade.
3. `research_2.pdf` (pp. 7–8) gated the behavioral sandbox behind the **A/B/C result of real sessions**:
   *"if users consistently prefer approval or sandbox summary and resist explicit receipts, kill
   receipts… the likely winner is the sandbox summary."* That is a question for humans, not personas.

The honest synthetic takeaway is narrower and correct: **"static-only" is the load-bearing assumption,
and the real sessions must test it head-on** (Step 2 artifact preference + a direct "is static enough to
change your decision?" probe). Built into [`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md).

---

## 3. Research Gatekeeper — drift audit vs `research_2.pdf`

| Category | Verdict | Note |
|---|---|---|
| CI guard as the wedge (pp. 6, 8) | ✅ PASS | No blocking gate sold as wedge; notifier is non-blocking + post-validation (`cli.py:393` exits 0). |
| Universal mandatory receipts (pp. 6, 8) | ✅ PASS | Receipts are one A/B/C variant under test, never headline. |
| Broad "AI-tool radar" (p. 6) | ✅ PASS | Radar explicitly demoted to the engine beneath the pack (`README.md`, `cli.py:47`). |
| **Behavioral-sandbox label (pp. 7–8)** | ⚠️ **DRIFT (minor)** | The A/B/C variant partners will rank is named **`sandbox_summary`** but the build ships a **static** read. Ranking a "sandbox" face the build can't back **confounds Step-2 data**. Fix = rename to `static_safety_summary`. (Pre-session fix #3.) |

**Bottom line:** the plan is research-compliant; the one drift is a *label*, not a strategy slip — but
it's load-bearing because it pollutes the exact metric Step 2 measures.

---

## 4. Demo Critic — the actionable find (copy-only CLI overclaims)

A simulated busy platform-eng ran the demo keyless/offline. It worked end-to-end (no crashes). But the
**CLI surface overclaims beyond the static, Claude-Code-only reality the docs admit to** — and two are
trust-detonators that the Copilot persona independently confirmed *"burns trust in the first 60 seconds."*

See the prioritized **PRE-SESSION FIX LIST (§7)**. The two blockers:
- `--client {claude-code,copilot,cursor}` emits **byte-identical Claude-Code config** for all three (the
  other clients don't read that schema). Selecting `copilot`/`cursor` silently produces a non-functional
  file under a client name.
- `[trial required]` / verdict word `trial` reads as *"the tool executed the server"* — it did not.

---

## 5. Synthetic Panel — objection map (NOT validation)

| Persona | Verdict | Step-2 artifact they'd keep | Step-3 export route | Hardest objection |
|---|---|---|---|---|
| Platform engineer | MODIFY | `formal_receipt` (grudging, auditability) | **Yes** — managed-settings via Jamf/MDM; blocker: `allowManagedMcpServersOnly:true` is aggressive | "Ship the behavioral sandbox before calling it a safety tool." |
| AppSec lead | MODIFY | `formal_receipt` (grudging timestamp anchor) | No — "a file I copy isn't a control surface; no push/revoke" | "Static = liability theater; I need to know if it exfiltrates source at runtime." |
| DevTools lead | KILL | none | No — "we push via Backstage/Terraform; a standalone JSON drifts" | "Feature, not a product — we'd build it as a portal plugin in a sprint." |
| Copilot/Cursor staff eng | MODIFY | `approval_only` (only honestly-scoped one) | No — Claude-only, useless to us | "Come back when you support my stack; niche inside a niche." |
| Skeptical CTO | KILL | (abstained) | n/a | "Anthropic owns the surface; absorbed in a quarter; no moat/flywheel/distribution." |

**Convergent objections, ranked by cross-agent corroboration:**
1. **Static ≠ behavioral** — 5/5 personas + the research's own deferred question. *Test in real sessions; do not pre-resolve.*
2. **CLI overclaims** — Demo Critic (2 blockers) + Copilot persona + Red Team. *Fixable copy; fix before sessions (§7).*
3. **Feature-not-a-company / incumbents absorb** — both KILLs + Red Team. *Positioning discipline (§6); defensible seam is repo-aware prioritization only.*
4. **Export-as-file ≠ control surface** — AppSec + DevTools ("no push/revoke", "drifts"). *Real signal — probe in Step 3 whether the* integration *matters more than the file.*

**Synthetic artifact tally** (for rehearsal only; the real one is in the ledger): receipt ×2 (both
grudging), approval-only ×1, none ×1, abstain ×1 — i.e. the research's predicted `sandbox_summary` win
did **not** appear, partly *because* the variant is mislabeled (DRIFT, §3). Another reason to fix #3
before measuring it for real.

---

## 6. Competitor Red Team — must-not-claim discipline

**Most dangerous collision: Anthropic's own managed config.** Every other incumbent is something Frontier
Scout sits *beside*; Anthropic owns the surface FS exports *into*. If they add native curation/ranking
(a one-sprint feature), the wedge collapses to a convenience wrapper at zero distribution cost to them.

**MUST NOT CLAIM** (each invites a comparison FS loses — use as session guardrails):
- "We **secure / sandbox / isolate** MCP servers" → ToolHive, Docker E2B, GitHub sandboxes do real isolation.
- "We **enforce** at runtime / per-request policy" → ToolHive & GitHub auto-enforcement own this; FS is static.
- "We **block installs** / gate at install-time" → Socket's chokepoint; FS is advisory.
- "We're **the registry / a verified catalog**" → Docker (300+ verified), GitHub, Official Registry (~2k entries).
- "We **own / manage / control** the allow-list" → it lives in Anthropic's client; FS only emits a fragment.
- "**Managed governance platform** for AI-tool adoption" → reframes FS as the compliance overhead that drives shadow usage (p. 3).
- "We **audit / give observability**" → ToolHive ships audit logs; FS has no telemetry plane.
- "**One-step cross-client export**" as a *capability* → it's **deferred** (Claude-only today); frame as roadmap, not feature.

**DEFENSIBLE SEAM** (the only ground to stand on — `research_2.pdf` p. 5):
- **Repo-aware prioritization** — ranks which servers matter *for this codebase* (filenames + AST imports). No incumbent reads the repo to decide. This is the one true seam.
- **Minimal safe-experiment recommendation** — a static capability+policy map as *decision support*, explicitly **not** enforcement.
- **Curation + export as a thin convenience layer** that *coexists with* (does not out-govern) incumbents.
- **Keyless / offline / static** as the honest scope boundary — a fast advisory pre-step, not a runtime/registry/enforcement product.

---

## 7. PRE-SESSION FIX LIST (copy-only — needs your authorization)

These are **wording/output-string fixes only — no logic, no deferred features, no behavioral sandbox,
no Copilot/Docker/CI build.** They are listed (not applied) because they touch user-facing strings in
code + their tests, and your rules said *don't write product code*. Each confounds a real session if left.

| # | Fix | Where | Type | Surfaced by |
|---|---|---|---|---|
| 1 | Drop or hard-gate `copilot`/`cursor` from `--client choices=` (emit "not implemented — claude-code only" to stderr) | `cli.py` choices= | code-string + test | Demo Critic BLOCKER · Copilot persona |
| 2 | Rename `[trial required]`→`[needs review — static only]`, verdict `trial`→`review-required`; put "no server executed" on the candidates line | `packs`/`cli.py` output | code-string + test | Demo Critic BLOCKER · AppSec ("decorative flag") |
| 3 | Rename proof variant `sandbox_summary`→`static_safety_summary` (+ the async-form label) | `proof_variants.py` + docs | code-string + doc | Gatekeeper DRIFT (confounds Step-2) |
| 4 | `signed-by`→`generated-by`; "ADOPTION RECEIPT"→"STATIC ASSESSMENT" | `proof_variants.py` | code-string + test | Demo Critic (false attestation) |
| 5 | Define or drop the undefined `(assess)` risk-lane parenthetical | `cli.py` sanction output | code-string | Demo Critic |
| 6 | Add a one-line `managed-settings.json` value-prop to `export` output (answers "why not edit `.mcp.json` myself") | `cli.py` export output | code-string | Demo Critic |

Priority for sessions: **#1 and #3 are mandatory** (they detonate trust / confound the headline metric).
#2, #4–#6 are high-value clarity. All are <1 line each.

---

## 8. What must NOT be built yet (even though the panel "asked")

| Tempting (synthetic demand) | Status | Why not |
|---|---|---|
| Behavioral MCP sandbox/trial | **BLOCKED — rule #1** | 5/5 personas demanded it; that's agent feedback, not validation. Gate on **real** Step-2 data. |
| Copilot / Docker / GitHub exports | **BLOCKED — rule #2** | Copilot persona demanded it; same logic. Fix #1 makes the demo honest *without* building it. |
| Blocking CI guard | **BLOCKED — rule #3** | Notifier stays non-blocking per `research_2.pdf`. |
| Any "secure/enforce/registry/govern" positioning | **AVOID — §6** | Invites an incumbent comparison FS loses. |

---

## 9. Recommendation

**MODIFY DEMO FIRST (copy-only, §7), then proceed to human sessions.** Not kill, not as-is.

- **Not KILL:** the synthetic KILLs are "incumbents absorb this" — a thesis-level worry the *real*
  sessions exist to refute or confirm. Simulated skeptics can't kill a thesis.
- **Not as-is:** the §7 overclaims (esp. #1 multi-client, #3 sandbox label) would confound Steps 2–3 and
  burn trust with exactly the kind of partner you most want (a Copilot/AppSec lead).
- **So:** authorize the copy-only fix list (#1 and #3 at minimum), then run the 5 sessions with
  [`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md) and record into
  [`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md). The real GO/KILL gate is unchanged and unmet: **0 / 5.**
