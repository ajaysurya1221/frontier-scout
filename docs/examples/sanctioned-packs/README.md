# Gold-path example — sanctioned MCP pack (Claude Code)

A real, end-to-end example of Frontier Scout's one narrow job, **generated from the CLI** (not
hand-written). **Static analysis only — no MCP server was executed to produce any of these files.**

## Scenario
A platform / AppSec lead at a GitHub-heavy org wants an approved set of MCP servers for their team's
**Claude Code**, ranked to their repo, with a static safety read, exported into the managed config they
already control.

## Reproduce it (keyless, offline)
```bash
frontier-scout packs candidates --repo . --client claude-code --json     # -> example-candidates.json
frontier-scout packs proof io.modelcontextprotocol/filesystem --repo .   # static safety summary
frontier-scout packs sanction io.modelcontextprotocol/time --repo . --client claude-code
frontier-scout packs sanction dev.sentry/sentry --repo . --client claude-code --acknowledge-risk
frontier-scout packs export --client claude-code --target ./out          # -> managed-settings.json + .mcp.json
```
The output is deterministic and offline; no network egress is required.

## The artifacts in this folder
| File | What it is |
|---|---|
| `example-candidates.json` | the repo-ranked candidate set (6 demo servers), each with a static verdict / risk / `requires_review` flag |
| `example-static-safety-summary.md` | one server's static capability + policy read (filesystem), labelled "no server was started or executed" |
| `example-claude-managed-config.json` | the **Claude Code managed-config fragment** (`allowedMcpServers` / `deniedMcpServers`) — for an admin to deploy |
| `example-project-mcp.json` | the project `.mcp.json` (per-repo; Claude Code requires user approval) |

## What this IS
- A **static** capability + policy read per server (no execution).
- A **Claude Code managed-config fragment** an admin/developer reviews and deploys through Claude's /
  enterprise control surface.
- A repo-aware **recommendation + translation** into a control plane you already own.

## What this is NOT
- **No MCP server was executed** to produce any of this — static analysis only.
- **Not runtime enforcement.** Frontier Scout *emits* the fragment; an admin *deploys* it; Claude Code's
  managed surface (or your MDM) does the enforcing. Frontier Scout enforces nothing.
- **Not market validation / not PMF.** This is a research-preview artifact.
- **Not cross-client.** Claude Code only today; Copilot / Cursor / Docker / GitHub allow-list are
  roadmap, not built.
