"""Typed envelopes shared by the platform planes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NodeKind = Literal["plan", "retrieve", "reason", "act", "review", "repair", "finalize"]
RiskLevel = Literal["low", "medium", "high"]


class Actor(BaseModel):
    id: str
    roles: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    source_id: str
    path: str
    line_start: int = 1
    line_end: int = 1
    checksum: str


class Citation(BaseModel):
    id: str
    text: str
    provenance: Provenance


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = "low"
    scope: str = "read"
    approved: bool = False


class NodeResult(BaseModel):
    node: NodeKind
    status: Literal["ok", "interrupt", "repaired", "failed"]
    output: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)
    cost_usd: float = 0.0
