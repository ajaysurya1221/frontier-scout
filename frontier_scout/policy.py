"""Shared policy-finding shape, reused across Frontier Scout.

The agent-firewall decision engine and receipts reuse :class:`PolicyFinding` and
:data:`Severity` as the canonical finding shape. (The former radar adoption-policy
engine that also lived here was removed with the radar.)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Severity = Literal["info", "medium", "high"]


class PolicyFinding(BaseModel):
    severity: Severity
    rule_id: str
    message: str
    tool_name: str = ""
