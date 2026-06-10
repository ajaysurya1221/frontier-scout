# KILL_CRITERIA.md

**Pre-registered on 2026-06-10.** This project is a research preview run as a falsifiable
bet, not a roadmap-driven product. This file states the bet, the gates, and what happens
on each outcome — published *before* the outcome is known, so the evaluation can't be
quietly moved. (The same honesty rule the verifier applies to agent PRs applies to the
project itself.)

## The bet

As AI coding agents open more PRs than humans can review line-by-line, teams will adopt —
and eventually pay for — a **neutral, fail-closed CI check that verifies an agent PR
stayed within an approved scope, backed by evidence that can be independently verified**
(signed via GitHub attestations, never self-asserted).

If that's wrong — if "AI review + green CI" turns out to be enough for everyone, or the
platforms ship it natively first — this project should stop, and say so in public.

## The gates (evaluate in public on or before 2026-09-08, day 90)

The bet survives only if **all four** hold:

1. **3 unaffiliated organizations** (no personal/work affiliation with the author) running
   the verifier on real PRs.
2. Each seeing **≥ 20 agent-authored PRs per week** through it.
3. **≥ 4 consecutive weeks of retention** (still running it without being chased).
4. **≥ 1 unprompted payment signal** ("can we pay for X" without being asked).

"Running it" means the Action or workflow on their default branch — not a demo, not a
friend's empty repo.

## Flip-to-quit (any two end the project early, before day 90)

- GitHub ships native session-evidence / scope verification for agent PRs in the merge
  box (artifact security scanning ≠ this; scope-vs-mandate verification = this).
- 25 cold conversations with maintainers / platform / security leads yield fewer than 3
  second meetings and zero unprompted installs.
- The platform evidence surfaces this depends on stay API-walled while the open ones break
  schema twice within the window.
- A distributed open-source project ships PR-diff↔action-record scope binding first — in
  which case the right move is to contribute, not compete.
- A structural conflict (e.g., employment IP) is asserted.

## Flip-to-double-down (any two justify going bigger than nights-and-weekends)

- ≥ 5 of the first 10 conversations pull toward payment or security/compliance use
  unprompted.
- A public incident where an agent PR with gamed CI ships a breach — independent
  verification becomes a board-level word.
- Auditor or regulator guidance explicitly requires agent-change evidence beyond a human
  PR approval.
- Organic traction: ≥ 1k stars or ≥ 50 real installs within the window.
- Agent vendors co-author a signed session-attestation standard — then evidence churn
  collapses and the fastest integrator wins.

## What happens on failure

A short public post-mortem in this file; the verifier core gets offered upstream to the
closest aligned open-source project; the repo is archived with its tests green. No quiet
pivot, no sixth identity.

## What happens on success

Incorporate, charge, and re-evaluate scope with the design partners — still under the
"emit, don't enforce; verify, don't guess" invariants in [AGENTS.md](AGENTS.md).
