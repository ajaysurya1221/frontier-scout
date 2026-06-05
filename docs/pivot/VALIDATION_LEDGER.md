# Validation Ledger — Sanctioned MCP Packs

> **Status: 0 / 5 real sessions logged.** This ledger holds **real external human** feedback only.
> Synthetic personas do **not** go here (see [`SYNTHETIC_VALIDATION_REPORT.md`](SYNTHETIC_VALIDATION_REPORT.md)).
> Run sessions with [`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md); record verbatim, not paraphrase.
>
> **The GO/KILL decision is not made until all 5 rows below are filled by 5 different real people.**

**Gate metrics (from `research_2.pdf` pp. 7–8):**
1. **Pack preference** — ≥ **3 / 5** prefer the pack to hand-curating `.mcp.json` / Slack / wiki.
2. **Proof artifact** — a clear **modal** variant they'd *voluntarily* keep (approval-only / static-safety-summary / formal-record / none).
3. **Export route** — ≥ **1 / 5** say "we could route this export through our actual process."

---

## Per-partner capture (copy one block per session)

### Partner 1
- **Name / role title:** ___
- **Org:** ___  · **Primary assistant:** Claude Code / Copilot / Cursor / other: ___
- **Repo archetype:** monorepo / polyrepo / OSS mix / enterprise — ___
- **Baseline process (their words):** ___
- **Approx steps / clock time to approve one new MCP server:** ___
- **Step 1 — pack preference:** prefer / neutral / no — notes: ___
- **Step 2 — kept artifact:** approval-only / static-safety-summary / formal-record / none / split (which) — notes: ___
- **Step 3 — export route:** yes (surface: ___) / no / "no surface yet" — notes: ___
- **Hardest objection:** ___
- **"What I'm most wrong about" (their words):** ___
- **Verbatim quote (the one sentence that captures their view):** "___"

### Partner 2
- **Name / role title:** ___
- **Org:** ___  · **Primary assistant:** Claude Code / Copilot / Cursor / other: ___
- **Repo archetype:** ___
- **Baseline process (their words):** ___
- **Approx steps / clock time:** ___
- **Step 1 — pack preference:** prefer / neutral / no — notes: ___
- **Step 2 — kept artifact:** approval-only / static-safety-summary / formal-record / none / split — notes: ___
- **Step 3 — export route:** yes (surface: ___) / no / "no surface yet" — notes: ___
- **Hardest objection:** ___
- **"What I'm most wrong about":** ___
- **Verbatim quote:** "___"

### Partner 3
- **Name / role title:** ___
- **Org:** ___  · **Primary assistant:** Claude Code / Copilot / Cursor / other: ___
- **Repo archetype:** ___
- **Baseline process (their words):** ___
- **Approx steps / clock time:** ___
- **Step 1 — pack preference:** prefer / neutral / no — notes: ___
- **Step 2 — kept artifact:** approval-only / static-safety-summary / formal-record / none / split — notes: ___
- **Step 3 — export route:** yes (surface: ___) / no / "no surface yet" — notes: ___
- **Hardest objection:** ___
- **"What I'm most wrong about":** ___
- **Verbatim quote:** "___"

### Partner 4
- **Name / role title:** ___
- **Org:** ___  · **Primary assistant:** Claude Code / Copilot / Cursor / other: ___
- **Repo archetype:** ___
- **Baseline process (their words):** ___
- **Approx steps / clock time:** ___
- **Step 1 — pack preference:** prefer / neutral / no — notes: ___
- **Step 2 — kept artifact:** approval-only / static-safety-summary / formal-record / none / split — notes: ___
- **Step 3 — export route:** yes (surface: ___) / no / "no surface yet" — notes: ___
- **Hardest objection:** ___
- **"What I'm most wrong about":** ___
- **Verbatim quote:** "___"

### Partner 5
- **Name / role title:** ___
- **Org:** ___  · **Primary assistant:** Claude Code / Copilot / Cursor / other: ___
- **Repo archetype:** ___
- **Baseline process (their words):** ___
- **Approx steps / clock time:** ___
- **Step 1 — pack preference:** prefer / neutral / no — notes: ___
- **Step 2 — kept artifact:** approval-only / static-safety-summary / formal-record / none / split — notes: ___
- **Step 3 — export route:** yes (surface: ___) / no / "no surface yet" — notes: ___
- **Hardest objection:** ___
- **"What I'm most wrong about":** ___
- **Verbatim quote:** "___"

---

## Tally (fill after all 5)

| Partner | Role / Org | Step 1 (prefer pack?) | Step 2 (kept artifact) | Step 3 (route export?) |
|---|---|---|---|---|
| 1 | | prefer / neutral / no | approval / static-summary / formal / none | yes / no |
| 2 | | prefer / neutral / no | approval / static-summary / formal / none | yes / no |
| 3 | | prefer / neutral / no | approval / static-summary / formal / none | yes / no |
| 4 | | prefer / neutral / no | approval / static-summary / formal / none | yes / no |
| 5 | | prefer / neutral / no | approval / static-summary / formal / none | yes / no |
| **Count** | | __ prefer / 5 | modal: __ | __ yes / 5 |
| **Threshold** | | ≥ 3 / 5 | clear modal | ≥ 1 / 5 |
| **Pass?** | | ☐ | ☐ | ☐ |

---

## Decision (only valid when all 5 rows are real)

- **GO (build the validated V1, in order):** Gate 1 **and** Gate 3 pass. Then, gated on Gate 2's modal:
  - modal = **static-safety-summary** → keep it as the headline; drop formal receipts.
  - modal = **formal-record** → build selective auto-records for high-risk servers only.
  - Only *then* consider the behavioral MCP probe (high-risk servers only) + a second client export.
- **KILL / re-scope (stop polishing):**
  - Gate 1 **< 3 / 5** → curation + repo-fit isn't pulling; re-scope to the narrowest sub-problem with repeated operational pull.
  - Gate 3 **0 / 5** → the export target is wrong; fix it (or pivot to feeding Docker/ToolHive catalogs) before anything else.
  - Partners say "we just need better policy data, not a product" → become middleware, not a surface.

**Decision recorded:** _______ (GO / MODIFY / KILL) · **Date:** _______ · **By:** _______

> Reminder: the agent will not fill this in. Only real sessions count.
