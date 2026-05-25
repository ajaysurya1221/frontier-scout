"""Typed tool definitions with scopes, allowlists, and approval gates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..authz.engine import AuthzEngine
from ..core.errors import ApprovalRequired
from ..core.types import ToolCall


class ToolDefinition(BaseModel):
    name: str
    scope: str
    risk: str = "low"
    requires_approval: bool = False
    mcp_server: str | None = None


class ToolRegistry:
    def __init__(self, authz: AuthzEngine, allowlisted_mcp_servers: set[str] | None = None) -> None:
        self.authz = authz
        self.allowlisted_mcp_servers = allowlisted_mcp_servers or set()
        self._tools: dict[str, tuple[ToolDefinition, Callable[[dict[str, Any]], dict[str, Any]]]] = {}

    def register(self, definition: ToolDefinition, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._tools[definition.name] = (definition, handler)

    def call(self, actor: str, call: ToolCall) -> dict[str, Any]:
        definition, handler = self._tools[call.name]
        if definition.mcp_server and definition.mcp_server not in self.allowlisted_mcp_servers:
            raise PermissionError(f"MCP server not allowlisted: {definition.mcp_server}")
        if not self.authz.can_call_tool(actor, definition.scope):
            raise PermissionError(f"{actor} cannot call {definition.scope} tool")
        if definition.requires_approval and not call.approved:
            raise ApprovalRequired(f"{definition.name} requires approval")
        return handler(call.args)


def read_only_plan_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "plan": args.get("plan", "")}

