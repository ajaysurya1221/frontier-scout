# Spike B — Claude Code MCP config schema (Phase 0, P0-4)

**Question:** what exact shapes must the exporter (`frontier_scout/exporters/claude_config.py`,
P2-1) emit so a sanctioned MCP-server pack "snaps into" a real Claude Code control plane?

**Source:** live Claude Code docs, fetched June 2026 —
<https://code.claude.com/docs/en/mcp> and <https://code.claude.com/docs/en/managed-mcp>.
Golden fixtures: `tests/fixtures/claude_config_project.json`, `tests/fixtures/claude_config_managed.json`.

## The three control surfaces (and which governs the real risk)

| Surface | File | Governs | Deployed by |
|---|---|---|---|
| **Managed allow/deny** (PRIMARY export) | `managed-settings.json` (`allowedMcpServers`/`deniedMcpServers`) | all scopes incl. **user-scoped** | admin / MDM / GPO |
| **Managed fixed set** | `managed-mcp.json` | exclusive set (same shape as `.mcp.json`) | admin / MDM / GPO |
| **Project** (SECONDARY export) | `.mcp.json` in repo root | project scope only (per-dev approval) | committed to VCS |
| User / local (NOT a target) | `~/.claude.json` | per-user, private | the user |

**Load-bearing finding (validates v3 plan):** user-scoped servers live in `~/.claude.json` and
are **private to the user** — a repo-committed `.mcp.json` cannot govern them. The
`allowedMcpServers`/`deniedMcpServers` managed surface is the **only** thing that reaches them, and
it is **admin-deployed**, not a repo file. So the exporter emits a *fragment an admin applies*, and
the product copy must say so.

## Shapes

### Project `.mcp.json` / `managed-mcp.json` (same format) — the `mcpServers` map
```json
{
  "mcpServers": {
    "github":     { "type": "http", "url": "https://api.githubcopilot.com/mcp/" },
    "filesystem": { "type": "stdio", "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "env": {} }
  }
}
```
- **stdio:** `command` (str), `args` (list), `env` (object). Optional `type: "stdio"`.
- **http:** `type: "http"` (alias `streamable-http`), `url`, optional `headers`.
- Env-var expansion: `${VAR}` / `${VAR:-default}` in command/args/env/url/headers.
- **Never** put secrets in `env` of a managed/committed file — use `${VAR}` or OAuth.

### Managed allow/deny (`managed-settings.json`) — the governance fragment
```json
{
  "allowManagedMcpServersOnly": true,
  "allowedMcpServers": [
    { "serverUrl": "https://api.githubcopilot.com/*" },
    { "serverCommand": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."] }
  ],
  "deniedMcpServers": [ { "serverName": "dangerous-server" } ]
}
```
- Each entry is an object with **one** key: `serverUrl` (supports `*` wildcards),
  `serverCommand` (exact arg array), or `serverName` (exact; **not** a security control alone —
  a user can label any server `github`, so prefer `serverUrl`/`serverCommand`).
- **Denylist wins** over allowlist. Unset allowlist = all allowed; `[]` = none allowed.
- `allowManagedMcpServersOnly: true` ignores user/project allowlists (denylist still merges).

## Exporter contract (for P2-1)

For a sanctioned pack scoped to `claude-code`, emit:
1. **`managed-settings.json` fragment** (PRIMARY): sanctioned servers → `allowedMcpServers`
   (prefer `serverUrl` for http, `serverCommand` for stdio); explicitly-unsanctioned → `deniedMcpServers`
   (use `serverName` from overrides). Set `allowManagedMcpServersOnly: true` for the
   approved-catalog pattern.
2. **`.mcp.json` map** (SECONDARY): sanctioned servers → `mcpServers` from `server_meta`
   (command/args/env or type/url).
- Run every emitted string through `outputs/_text.sanitize_sensitive_text` before writing.
- Managed-config on-disk paths (for the README/quickstart, not written by us):
  macOS `/Library/Application Support/ClaudeCode/`, Linux `/etc/claude-code/`,
  Windows `C:\Program Files\ClaudeCode\`.
