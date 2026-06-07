"""Render a managed Claude Code MCP allow/deny fragment from a repo policy.

The compiler turns ``AgentPolicy.mcp_server_allowlist`` (bare server names) into a
managed-settings fragment (``allowManagedMcpServersOnly`` / ``allowedMcpServers`` /
``deniedMcpServers``). Shapes track the live Claude Code docs
(``docs/spike-claude-config.md`` + ``tests/fixtures/claude_config_*.json``).
Frontier Scout emits this; Claude Code enforces it.
"""

from __future__ import annotations

import re

__all__ = ["to_managed_config_from_names", "server_key"]


def server_key(name: str) -> str:
    """A short, config-safe key (the last path segment of a server name)."""

    segment = name.replace("\\", "/").rstrip("/").split("/")[-1]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", segment).strip("-").lower()
    return slug or "server"


def to_managed_config_from_names(
    allowed: list[str], *, denied: list[str] | None = None, allow_managed_only: bool = True
) -> dict[str, object]:
    """Render a managed allow/deny fragment from bare server names.

    A name match is the only honest entry available without transport metadata —
    a managed allowlist keyed by ``serverName``.
    """

    return {
        "allowManagedMcpServersOnly": allow_managed_only,
        "allowedMcpServers": [{"serverName": server_key(name)} for name in allowed],
        "deniedMcpServers": [{"serverName": server_key(name)} for name in (denied or [])],
    }
