# Human Validation Script — Sanctioned MCP Packs

> **This is the real one.** Everything here is for **5 sessions with real external humans**. The
> rehearsal in [`SYNTHETIC_VALIDATION_REPORT.md`](SYNTHETIC_VALIDATION_REPORT.md) was synthetic and does
> **not** count. Record results in [`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md). For the command-by-command
> facilitation mapping, this complements [`../validation-session-kit.md`](../validation-session-kit.md) —
> that file maps each step to the exact CLI; this file is the **outreach + call script + objection rehearsal**.

**ICP:** platform-eng / AppSec leads at GitHub-heavy orgs whose devs use Claude Code (and/or Copilot).
**Goal:** learn whether they'd prefer a repo-ranked, risk-checked sanctioned MCP pack + managed-config
export over hand-curating `.mcp.json`. **Not** to sell.

> ✅ **Honesty fixes landed (2026-06-05 claim-honesty hardening sprint):** `--client copilot/cursor`
> now hard-errors instead of emitting Claude config under another client's name, and the static proof
> variant is named `static_safety_summary` (not "sandbox"). This script uses the honest labels
> throughout. See [`CLAIM_HONESTY_HARDENING_REPORT.md`](CLAIM_HONESTY_HARDENING_REPORT.md).

---

## Honest scope (say this verbatim if asked "what does it actually do?")

- **Claude Code first.** Copilot/Cursor export is **roadmap, not built.** Do not imply otherwise.
- The safety read is **static** (capability + policy from declared metadata) — it **does not execute**
  the server. It is decision *support*, not behavioral proof or enforcement.
- It **does not block** anything (no CI gate, no install gate). It ranks, reads, and exports a config fragment.
- Keyless, offline, zero egress — nothing to install-trust, nothing phones home.

---

## 1. Cold DM (~100 words)

> Hey {FirstName} — quick question, not a pitch:
>
> How does your team decide which MCP servers are safe to use in Claude Code? I mean the step between
> "a dev found a cool server" and "it's in the managed config" — for most platform/AppSec folks I've
> talked to that's Slack threads + manual review + someone eventually updating a wiki.
>
> I'm running 5 short design-partner calls (20 min) to test whether a different approach is worth
> building. No install, no account — I just want to hear how you handle it today.
>
> Worth 20 minutes? {CalendarLink}
>
> — {YourName}

---

## 2. Email (subject + ~250 words)

**Subject: 20 min — how does your team vet MCP servers for Claude Code?**

> Hi {FirstName},
>
> I'm a solo dev building tooling in the Claude Code / MCP space, and I'm in early validation — trying
> to understand a real workflow problem before writing more code.
>
> Specific question: at {Org}, when a developer wants to add a new MCP server to Claude Code, what
> actually happens? Who approves it, what gets checked, how long does it take, and what does "approved"
> end up looking like — a wiki page, a shared `.mcp.json`, a Slack message everyone hopes gets read?
>
> I have a rough prototype of something different: a local CLI — keyless, fully offline — that takes
> candidate MCP servers, ranks them by fit to your repo, runs a **static** safety read (declared
> permissions, policy, supply-chain flags), and exports the approved set into a Claude **managed config**
> fragment. Nothing installs, nothing calls home. To be upfront: it's Claude-Code-first, the safety read
> is static (it does not run the server), and it doesn't block anything.
>
> 15–20 minutes would be genuinely useful. I'll show you the current output and ask you to tell me where
> it breaks down. No pitch, no follow-up deck. If a call doesn't fit, I can send 6 async questions
> instead (<5 min).
>
> Easy to say no — just don't reply, no follow-up sequence.
>
> {CalendarLink}
>
> — {YourName}

---

## 3. Async validation form (6 questions, <5 min)

Use for partners who won't take a call. Neutral wording — you want truth, not agreement.

**Intro:** *I'm validating a tool concept and want honest signal, not confirmation. No right answers.
Skip anything you can't answer.*

1. **Baseline.** When a developer at your org wants a new MCP server in Claude Code, walk me through what
   actually happens — who's asked, what's checked, how the approved state is recorded, and roughly how
   many steps / how much clock time from request to "yes." *(Free text — "it's a Slack DM and we wing it"
   is a valid answer.)*
2. **Biggest friction.** Which part of that is most annoying, inconsistent, or most likely to get skipped
   under pressure? *(Free text.)*
3. **Pack vs current process.** Imagine a CLI that takes candidate MCP-server repos, runs a local static
   read (declared permissions, policy, supply-chain flags), ranks them by fit to your repo, and outputs a
   ranked, annotated list. For approving a new server, which would you prefer?
   ☐ The CLI output — I'd rather start from a ranked, annotated list ☐ My current process — not broken
   enough to change ☐ Depends (note what) ☐ No opinion
4. **Which artifact would you actually keep?** After an approval decision, which would you keep on record?
   ☐ A. **Approval-only** — a clean `.mcp.json` of only approved servers ☐ B. **Static safety summary** —
   what each server declared it needs (network/filesystem/env) + a pass/flag/warn verdict ☐ C. **Formal
   record** — who approved, timestamp, version pinned, flags reviewed ☐ D. None. *(One sentence on why,
   if you picked one.)*
5. **Managed-config export.** If it exported the approved set into however your org distributes managed
   Claude Code config (repo, secrets manager, MDM profile, dotfiles `.mcp.json`…), useful? ☐ Yes — we'd
   route it via ______ ☐ Maybe — depends on ______ ☐ No — no centralized surface yet ☐ No — wouldn't want
   a tool touching our config pipeline
6. **What did I get wrong?** Any part of this workflow I'm misunderstanding, or a constraint that would
   make or break it for you? *(Free text — the most useful question here.)*

---

## 4. Live-call script (30 min, timeboxed)

**Pre-call:** open a blank doc for **verbatim quotes**. Do **not** screen-share until 3:00. Do **not**
pitch — if you catch yourself explaining why it's good, stop and ask a question instead.

### Block 1 — Baseline (0–3 min) · *scores nothing; calibration*
> "Before I show you anything — when a dev wants a new MCP server in Claude Code, what actually happens?
> Who's asked, what's checked, what does 'approved' look like? And roughly how long, start to finish?"

Listen for: is there *any* formal step, or is it tribal? Person-gated or process-gated? Does "approved"
produce an artifact or live in someone's head? **Don't advance without a rough step count + time.**

### Block 2 — Candidates + static safety (3–13 min) · *scores Gate 1 (≥3/5 prefer pack)*
Share screen: `packs candidates --repo {RepoOrArchetype} --client claude-code` → ranked list + static map.
> "For the servers your team actually uses or is weighing — does starting from this change how you'd run
> the approval conversation, or does it mostly duplicate what you'd check anyway?"
> "Anything here you'd trust *less* than your current process? Anything you'd trust *more*?"

Listen for: "we'd still check X ourselves" = a gap, not a rejection. "I'd send this to {stakeholder}" =
strong. "We don't approve at this granularity" = the unit of approval is teams, not servers. "Our real
concern is runtime, not static" = the **central hypothesis** — record it precisely. Mark prefer/neutral/no
silently.

### Block 3 — Proof A/B/C (13–22 min) · *scores Gate 2 (modal artifact)*
Show all three, **without signalling a favorite**:
> "A: a clean `.mcp.json` of only approved servers — drop into managed config, done."
> "B: a **static safety summary** — what each server declared it needs, with pass/flag/warn." *(CLI
> variant key: `static_safety_summary` — it is static analysis, no server executed; say so.)*
> "C: a formal record — who approved, when, version pinned, which flags were reviewed."
> "If you had to keep one on record, which? And which is least useful?"

Do **not** ask "would any of these be useful?" (leading). Listen for role signal (AppSec→C, platform→A,
"none"→approval is social not document-driven). "I'd want B to review and A to deploy" = split use case,
record it exactly.

### Block 4 — Managed-config export (22–28 min) · *scores Gate 3 (≥1/5 routes it)*
> "If this exported the approved set into however you distribute Claude Code config today — where would
> that land? A repo, secrets manager, MDM profile, dotfiles repo, anything?"

Listen for: a specific surface named (even vaguely) = yes. "We don't have that yet" = not a no; the
distribution problem is *also* unsolved. "We'd want to own the export step, not have the tool push it" =
they want output, not integration — record the distinction (this was the synthetic AppSec/DevTools
objection; see if it's real).

### Block 5 — Close (28–30 min)
> "What's the thing I'm most wrong about in how I framed this?" *(Not a courtesy — wait for a real answer.)*
> "Okay if I follow up with a short async question in a few weeks?"

Don't summarize their words back in a positive frame. Thank them, close.

---

## 5. Objection-rehearsal cheatsheet (from the synthetic sprint)

Real partners will likely hit these. **Answer honestly — do not spin.** The honest answer is the point.

| Likely objection | Honest response (NOT a defense) |
|---|---|
| "Static isn't enough — I need to know what it *does* at runtime." | "Agreed — that's the open question. Today it's static decision-support, not behavioral proof. Whether you'd need behavioral evidence to actually sanction a write/credential server is exactly what I'm here to learn — would you?" *(This is Gate-2/hypothesis gold. Let them talk.)* |
| "Isn't this just Anthropic's managed config / GitHub's registry?" | "For discovery and the allow-list surface — yes, they own that, and I export *into* it rather than replace it. The only thing I do that they don't is rank by *your repo*. Is repo-fit ranking worth anything to you, or is it noise?" |
| "Feature, not a product — we'd build it in a sprint." | "Maybe. If you'd build it in a sprint, that itself tells me something — would you actually, or is it always the thing that never gets prioritized?" |
| "It's Claude-only; we use Copilot/Cursor." | "True today — Claude-Code-first, other clients are roadmap. Is the curation/ranking useless to you without a Copilot export, or is the ranked safety read worth something client-agnostic?" |
| "A file I copy isn't a control surface — no push, no revoke." | "Right — it emits a fragment, it doesn't push or enforce. Where would the handoff need to be for it to fit your real distribution?" |

---

## 6. Facilitator guardrails — do NOT claim (from the red team)

To avoid an incumbent comparison you lose, **never** say in a session: "we secure/sandbox/isolate
servers," "we enforce at runtime," "we block installs," "we're the registry/a verified catalog," "we own
your allow-list," "managed governance platform," "we audit MCP usage," or "one-step cross-client export"
(it's deferred). Stick to: **repo-aware ranking + static safety read + a managed-config export fragment
that coexists with your existing tools.**
