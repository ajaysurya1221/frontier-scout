# Validation harness dry-run (rehearsal — NOT partner data)

> This is a **facilitator rehearsal** of [`validation-protocol.md`](validation-protocol.md) run by
> the agent against the **offline demo pack** to prove every step works and yields the right
> artifact. It contains **no real design-partner preferences and no go/no-go result** — those come
> only from the 5 human sessions (see [`validation-session-kit.md`](validation-session-kit.md)).

Environment: a throwaway `FRONTIER_SCOUT_HOME`, a temp repo with a `.mcp.json`,
`FRONTIER_SCOUT_TELEMETRY=1`. Keyless, offline.

## Step 1 — pack pull ✅
`frontier-scout packs candidates --repo "$REPO" --client claude-code`
```
Repo-ranked mcp servers for claude-code (6):
- io.modelcontextprotocol/filesystem  fit=high risk=medium stdio  [needs review — static only]
- io.modelcontextprotocol/fetch  fit=high risk=medium stdio  [needs review — static only]
- io.modelcontextprotocol/time  fit=high risk=medium stdio
- io.modelcontextprotocol/sqlite  fit=high risk=medium stdio  [needs review — static only]
- com.github/github  fit=high risk=medium http  [needs review — static only]
- dev.sentry/sentry  fit=high risk=medium http  [needs review — static only]
```
*Artifact present:* a repo-ranked list with per-server static safety (`[needs review — static only]` flags the
high-risk ones). ← what a partner reacts to in step 1.

## Step 2 — proof variant (A/B/C) ✅
`frontier-scout packs proof io.modelcontextprotocol/filesystem --repo "$REPO"` renders all three:
```
===== proof variant: approval_only =====
io.modelcontextprotocol/filesystem: ALLOW (verdict trial, risk medium). Approve this server for the team?
===== proof variant: static_safety_summary =====
## Static safety analysis — io.modelcontextprotocol/filesystem
===== proof variant: formal_receipt =====
STATIC ADOPTION ASSESSMENT
```
`… --keep static_safety_summary` → `Recorded proof-variant preference: static_safety_summary`.
*Artifact present:* three distinct faces + a recorded choice. ← the A/B/C the partner picks from.

## Step 3 — sanction + export snap-in ✅
```
Sanctioned io.modelcontextprotocol/time (assess) for claude-code.        # low-risk: direct
Sanctioned io.modelcontextprotocol/filesystem (trial) for claude-code.   # high-risk: --acknowledge-risk
```
`frontier-scout packs export --client claude-code --target ./out` → `managed-settings.json`:
```json
{
  "allowManagedMcpServersOnly": true,
  "allowedMcpServers": [
    { "serverCommand": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."] },
    { "serverCommand": ["uvx", "mcp-server-time"] }
  ],
  "deniedMcpServers": []
}
```
*Artifact present:* a valid admin-deployable allow/deny fragment + a project `.mcp.json`. ← what a
partner judges "could I route this through my process?" against.

## Step 4 — funnel ✅
`frontier-scout stats`
```
Sanctioned-pack funnel (6 events):
  candidates_viewed: 1   safety_viewed: 1   sanctioned: 2
  sanction_blocked: 0    unsanctioned: 0    exported: 1   proof_variant_kept: 1
```
*Artifact present:* the opt-in funnel recorded every step of the session locally.

## Verdict (harness only)

Every protocol step is runnable and produces the artifact the partner reacts to; the instrumentation
captures the funnel. **The harness is ready for the 5 human sessions.** The go/no-go decision is
deferred to those sessions, per the protocol's kill criteria — the agent does not and will not
fabricate it.
