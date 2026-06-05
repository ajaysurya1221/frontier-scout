# Validation session kit (run-it-yourself)

The facilitator's runbook for the 2-week protocol in [`validation-protocol.md`](validation-protocol.md).
This kit makes the protocol **runnable**: an exact per-partner script mapped to real commands, a
capture template, and a decision-gate scorer. **You** run the 5 sessions and record what partners
actually say — the agent built and proved the tooling but cannot be the partners or invent results.

## Before any session

```bash
pipx install frontier-scout          # or, from this branch: pip install -e ".[dev]"
export FRONTIER_SCOUT_TELEMETRY=1    # local-only funnel; nothing phones home
```
Recruit 5 **platform-eng / AppSec leads** at GitHub-heavy orgs using Claude Code (and/or Copilot).
Have each partner's real repo path handy (`$REPO`).

## Per-partner session script (~30 min)

**0 · Baseline (ask first, before showing the tool).** "How do you decide and roll out a new MCP
server for your team today, and how long does it take?" Record the process + minutes.

**1 · Pack pull** — *success: ≥3/5 prefer this to hand-curation.*
```bash
frontier-scout packs candidates --repo "$REPO" --client claude-code
```
Show the repo-ranked list + per-server static safety read. Ask: *"Would you rather use this than
hand-curate `.mcp.json` / a Slack thread / a wiki page?"* Record **prefer / neutral / no**.

**2 · Proof variant (A/B/C)** — *success: a variant they'd voluntarily keep.*
```bash
frontier-scout packs proof <server> --repo "$REPO"          # shows all 3 variants
```
Show the three faces (approval-only · sandbox-summary · formal-receipt). Ask: *"Which of these would
you actually keep on file?"* Then record their pick:
```bash
frontier-scout packs proof <server> --repo "$REPO" --keep <approval_only|sandbox_summary|formal_receipt>
```
(The research predicts `sandbox_summary` wins; if they resist `formal_receipt`, that's the signal to
drop "receipts" as a headline.)

**3 · Export snap-in** — *success: ≥1 team says "we could route this through our process."*
```bash
frontier-scout packs sanction <server> --repo "$REPO" [--acknowledge-risk]
frontier-scout packs export --client claude-code --target ./out
cat ./out/managed-settings.json     # the admin-deployed allow/deny fragment
cat ./out/.mcp.json                 # the project face
```
Ask: *"Could you route this export through your current process (MDM/managed settings, or a
committed `.mcp.json`)?"* Record **yes (which surface) / no**.

**Close.** `frontier-scout stats` to confirm the funnel recorded the session.

## Per-partner capture template (copy one block per partner)

```
Partner #: ____   Role: ____   Client: claude-code/copilot   Repo archetype: ____
Baseline: current process = ____________   time/steps = ____
Step 1 pack-pull preference:   prefer / neutral / no        notes: ____
Step 2 kept variant:           approval_only / sandbox_summary / formal_receipt   notes: ____
Step 3 export snap-in:         yes (managed / project) / no    notes: ____
Verbatim quote: "________________________________________"
```

## Decision-gate scorer (after all 5)

Tally across partners:

| Metric | Threshold | Count | Pass? |
|---|---|---|---|
| Step 1 — prefer pack to hand-curation | **≥ 3 / 5** | __ / 5 | ☐ |
| Step 2 — voluntarily keep a variant (note which) | ≥ 1, and a clear modal choice | __ | ☐ |
| Step 3 — ≥1 team routes the export | **≥ 1 / 5** | __ / 5 | ☐ |

- **GO (build Phase-4 V1):** Step 1 **and** Step 3 pass. Then build, in order: the behavioral MCP
  probe (high-risk servers only, `docs/spike-mcp-probe.md`), Copilot + GitHub allow-list exporter,
  non-blocking notifier. If Step 2's modal choice is `sandbox_summary`, keep it as the headline and
  drop formal receipts; if `formal_receipt`, build selective auto-receipts for high-risk servers.
- **KILL / re-scope (do NOT keep polishing):**
  - Step 1 **< 3/5** → curation+repo-fit isn't pulling; re-scope to the narrowest sub-problem with
    repeated operational pull.
  - Step 3 **0/5** → the export target/integration is wrong; fix it (or pivot to feeding
    Docker/ToolHive catalogs) before anything else.
  - Partners say "we just need better policy data, not a product" → become middleware, not a surface.

## What the agent did vs what is yours

Built + proved (this kit + `tests/`): the `candidates / proof / sanction / export / stats` commands,
the three rendered proof variants, the opt-in funnel, and a full dry-run
([`validation-dry-run.md`](validation-dry-run.md)). **Yours:** recruit the 5 partners, run the
sessions, record real preferences, apply the scorer. The agent will not fabricate partner data.
