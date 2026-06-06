# Gold-path example — agent adoption firewall + audit trail

A real, end-to-end example of the **`frontier-scout agent`** workflow, **generated from the CLI** (not
hand-written). **Static analysis only — nothing was executed, no agent task was run, no MCP server was
started, and no secret value was read to produce any of these files.**

## Scenario
A platform / AppSec lead wants to safely let AI coding agents work in a repo that contains secrets (`.env`),
CI workflows, database migrations, and a Dockerfile. They want a conservative starting policy, a way to
pre-check what an agent task proposes to do, and an audit receipt for each decision — **before** any agent
touches code, credentials, CI, or deploy config.

## Reproduce it (keyless, offline)
```bash
frontier-scout agent scan --repo . --json                 # -> scan-output.json
frontier-scout agent policy init --repo .                  # -> frontier-scout.policy.json
frontier-scout agent check "read the README and summarize the module layout"   # -> allow
frontier-scout agent check "run the test suite and report failures"            # -> needs_approval
frontier-scout agent check "modify the CI workflow to add a deploy step and run rm -rf build"  # -> block
frontier-scout agent receipts list                        # the audit trail
frontier-scout agent export claude --target ./out         # -> CLAUDE.policy.md (advisory snippet)
```
The output is deterministic and offline; no network egress is required.

## The artifacts in this folder
| File | What it is |
|---|---|
| `scan-output.json` | the static risk-surface scan (`.env` secret-likely, CI, migrations, Dockerfile, MCP config, agent config), each with a risk level + policy implication |
| `frontier-scout.policy.json` | the **conservative starter policy** generated from the scan (protects secrets/CI/migrations/deploy, blocks dangerous shell, deny-by-default MCP allowlist, gates risky surfaces) |
| `check-allow.json` | a read-only task → **allow** (no dangerous capability, no protected path) |
| `check-needs-approval.json` | a task that implies the **shell** capability → **needs_approval** (gated, not blocked) |
| `check-block.json` | a task referencing `rm -rf` + touching CI → **block** (`shell.blocked` + `path.protected`) |
| `sample-receipt.json` | the JSON audit receipt for one decision (verdict, reasons, files, redacted task text, git metadata, version) |
| `CLAUDE.policy.md` | the **advisory** policy snippet you can paste into a repo's `CLAUDE.md` |

## What this IS
- A **static** repo risk scan + a **conservative, editable** policy object (`frontier-scout.policy.json`).
- A **pre-flight check** that maps a *proposed* agent task to `allow` / `needs_approval` / `block`, with
  human-readable reasons — **without ever running the task**.
- A **local audit trail**: one JSON receipt per decision under `.frontier-scout/receipts/`.

## What this is NOT
- **Nothing is executed.** `scan` and `check` run no subprocess, no MCP server, no agent task, no network.
  (The only subprocess anywhere is a guarded read-only `git rev-parse` to stamp a receipt's branch/commit.)
- **Not runtime enforcement.** A `block` verdict is *advisory output*, not a kill-switch. Frontier Scout
  **emits** policy and evidence; it does **not** enforce anything at runtime. The exported `CLAUDE.policy.md`
  is documentation an agent/human reads, not a control Claude Code obeys.
- **No secret values.** Secret-likely files are detected by **name/path only**; their contents are never
  opened, read, or emitted, and persisted task text is redacted.
- **Not enterprise-grade / not compliance / not complete protection / not market-validated.** This is a
  research-preview artifact.
