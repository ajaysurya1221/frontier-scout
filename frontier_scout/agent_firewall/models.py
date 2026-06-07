from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from frontier_scout.policy import PolicyFinding  # reuse the canonical finding shape

Severity = Literal["info", "low", "medium", "high"]
Verdict = Literal["allow", "needs_approval", "block"]


class RiskSurface(BaseModel):
    path: str
    kind: str
    risk: Severity
    reason: str
    policy_implication: str
    suggested_checks: list[str] = Field(default_factory=list)


class ScanResult(BaseModel):
    repo: str
    surfaces: list[RiskSurface] = Field(default_factory=list)
    detected_checks: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    static_only: bool = True


class AgentPolicy(BaseModel):
    version: int = 1
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    allowed_shell_commands: list[str] = Field(default_factory=list)
    blocked_shell_commands: list[str] = Field(default_factory=list)
    allowed_file_globs: list[str] = Field(default_factory=list)
    protected_file_globs: list[str] = Field(default_factory=list)
    mcp_server_allowlist: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    approval_gates: list[str] = Field(default_factory=list)
    policy_notes: str = ""


class TaskDecision(BaseModel):
    verdict: Verdict
    summary: str
    reasons: list[PolicyFinding] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)
    dangerous_flags: list[str] = Field(default_factory=list)
    files_considered: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    static_only: bool = True


class Receipt(BaseModel):
    receipt_id: str
    timestamp: str
    repo: str
    git_branch: str | None = None
    git_commit: str | None = None
    task_summary: str
    policy_path: str | None = None
    verdict: Verdict
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    files_considered: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    frontier_scout_version: str | None = None
    kind: Literal["static-policy-assessment", "agent-action"] = "static-policy-assessment"
    # Binds a receipt to the exact policy in force when it was written (sha256 from
    # the policy lock). The verifier rejects receipts whose hash drifts from the lock.
    policy_hash: str | None = None
    # Action-receipt fields (kind == "agent-action"), written by the native hook for a
    # real tool call. Unused by the static ``agent check`` assessment, so all optional.
    tool_name: str | None = None
    tool_input_hash: str | None = None
    decision: str | None = None  # native permission decision: allow | deny | ask
    realized: dict[str, Any] | None = None  # PostToolUse outcome (exit, changed files, …)
