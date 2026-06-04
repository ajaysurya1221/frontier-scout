# Quickstart — sanctioned MCP-server packs (5 minutes, keyless)

Build your team's approved set of MCP servers for a coding assistant, vet each one's static
safety, and export the approved set into the managed config you already control. **No API key,
no network needed** — the flow defaults to a curated offline demo pack of real, popular MCP
servers. Add `--discover` to pull live servers from the MCP registry.

## 1. See the repo-ranked candidates

```bash
frontier-scout packs candidates --repo . --client claude-code
```

Servers are ranked by fit to *your* repo (the local tree-sitter profile — your source never
leaves the machine) and each shows a **static safety read** (capability map + policy verdict).
Add `--json` for machine output, `--discover` to also fetch live MCP-registry servers.

## 2. Sanction the ones you approve (risk-gated)

```bash
frontier-scout packs sanction io.modelcontextprotocol/time --repo .          # low-risk: approved
frontier-scout packs sanction io.modelcontextprotocol/filesystem --repo .    # high-risk: blocked...
frontier-scout packs sanction io.modelcontextprotocol/filesystem --repo . --acknowledge-risk
```

Low-risk servers sanction directly. A server with a **write / shell / credential / network**
capability is **blocked** until you review its static safety summary and re-run with
`--acknowledge-risk` (`--approver`/`--reason` are recorded in the decision). Reverse with
`frontier-scout packs unsanction <server>`.

## 3. Export into your control plane

```bash
frontier-scout packs export --client claude-code --target ./mcp-config
```

Writes two faces into `./mcp-config/`:

- **`managed-settings.json`** (primary) — `allowedMcpServers` / `deniedMcpServers`, the
  admin/MDM-deployed surface that governs even **user-scoped** (`~/.claude.json`) installs. Deploy
  it to `/Library/Application Support/ClaudeCode/`, `/etc/claude-code/`, or
  `C:\Program Files\ClaudeCode\` (see `docs/spike-claude-config.md`).
- **`.mcp.json`** (secondary) — a project-scoped `mcpServers` map for the repo.

> **Honest scope:** a repo-committed `.mcp.json` governs only project-scoped servers; the
> **managed** allow/deny fragment is what reaches user-scoped installs, and it is applied by an
> admin — Frontier Scout emits the fragment, your platform deploys it.

## Optional: measure the funnel (local, opt-in)

```bash
export FRONTIER_SCOUT_TELEMETRY=1     # off by default; local-only, nothing phones home
frontier-scout stats                  # candidates_viewed -> sanctioned/blocked -> exported
```

## Not yet (validated-then-built)

A **behavioral** sandbox trial (actually starting an MCP server and listing its tools) is a gated
V1 build — today's safety read is **static** (capability + policy). See `docs/spike-mcp-probe.md`
and `docs/validation-protocol.md`.
