"""Export a sanctioned MCP-server pack into Claude Code control-plane config.

Primary face: managed allow/deny (``allowedMcpServers`` / ``deniedMcpServers``) — the
admin/MDM-deployed surface that actually governs user-scoped (`~/.claude.json`) installs.
Secondary face: a project ``.mcp.json`` ``mcpServers`` map. Shapes are pinned by
``docs/spike-claude-config.md`` + ``tests/fixtures/claude_config_*.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from outputs._text import sanitize_sensitive_text


def _server_key(name: str) -> str:
    """A short, config-safe key (the last path segment of a server name)."""

    segment = name.replace("\\", "/").rstrip("/").split("/")[-1]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", segment).strip("-").lower()
    return slug or "server"


def _url_pattern(url: str) -> str:
    """Collapse a server URL to a ``scheme://host/*`` allowlist wildcard.

    Uses the bare host (never ``netloc``) so an embedded ``user:pass@`` userinfo
    can't leak credentials into the exported managed config.
    """

    parsed = urlparse(url)
    if parsed.scheme and parsed.hostname:
        host = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
        return f"{parsed.scheme}://{host}/*"
    return url or "*"


def _allow_entry(server) -> dict:
    meta = server.server_meta or {}
    transport = meta.get("transport")
    if transport in ("http", "sse") and meta.get("url"):
        return {"serverUrl": _url_pattern(str(meta["url"]))}
    if transport == "stdio" and meta.get("command"):
        return {"serverCommand": [str(meta["command"]), *[str(a) for a in meta.get("args", [])]]}
    # Unknown transport: a name match is weak (a user can relabel), but it's the
    # only honest entry we can emit without a URL or command.
    return {"serverName": _server_key(server.tool_name)}


def _project_entry(server) -> dict | None:
    meta = server.server_meta or {}
    transport = meta.get("transport")
    if transport in ("http", "sse") and meta.get("url"):
        entry: dict = {"type": "http" if transport == "http" else "sse", "url": str(meta["url"])}
        headers = meta.get("headers")
        if isinstance(headers, dict) and headers:
            entry["headers"] = dict(headers)
        return entry
    if transport == "stdio" and meta.get("command"):
        return {
            "type": "stdio",
            "command": str(meta["command"]),
            "args": [str(a) for a in meta.get("args", [])],
            "env": dict(meta.get("env") or {}),
        }
    return None  # unknown transport: not runnable, omit from the project map


def to_managed_config(servers, *, denied: list[str] | None = None, allow_managed_only: bool = True) -> dict:
    """Render a managed-settings allow/deny fragment for a sanctioned server set."""

    return {
        "allowManagedMcpServersOnly": allow_managed_only,
        "allowedMcpServers": [_allow_entry(s) for s in servers],
        "deniedMcpServers": [{"serverName": name} for name in (denied or [])],
    }


def to_project_mcp_json(servers) -> dict:
    """Render a project ``.mcp.json`` ``mcpServers`` map for a sanctioned server set."""

    mcp_servers: dict[str, dict] = {}
    for server in servers:
        entry = _project_entry(server)
        if entry is None:
            continue
        key = _server_key(server.tool_name)
        if key in mcp_servers:
            # de-collide: two namespaced server names can share a last path segment.
            suffix = 2
            while f"{key}-{suffix}" in mcp_servers:
                suffix += 1
            key = f"{key}-{suffix}"
        mcp_servers[key] = entry
    return {"mcpServers": mcp_servers}


def export_claude_config(
    servers,
    *,
    denied: list[str] | None = None,
    target_dir: Path | str,
    allow_managed_only: bool = True,
) -> dict[str, str]:
    """Write both faces to ``target_dir`` (redacted) and return their paths."""

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    managed = to_managed_config(servers, denied=denied, allow_managed_only=allow_managed_only)
    project = to_project_mcp_json(servers)
    managed_path = target / "managed-settings.json"
    project_path = target / ".mcp.json"
    managed_path.write_text(sanitize_sensitive_text(json.dumps(managed, indent=2)) + "\n")
    project_path.write_text(sanitize_sensitive_text(json.dumps(project, indent=2)) + "\n")
    return {"managed": str(managed_path), "project": str(project_path)}
