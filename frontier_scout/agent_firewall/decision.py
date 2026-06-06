"""Static, deterministic task-decision engine (the ``agent check`` verb).

``evaluate_task`` evaluates a *proposed* agent task against an
:class:`~frontier_scout.agent_firewall.models.AgentPolicy` and returns a
:class:`~frontier_scout.agent_firewall.models.TaskDecision` of
``allow | needs_approval | block``.

It is **static and advisory** — it never executes the task, never runs an MCP
server, never spawns a subprocess, and never touches the network or an LLM. The
verdict is derived purely from string/glob inspection of the task text and the
proposed ``changed_files``, reusing the canonical risk taxonomy
(:func:`frontier_scout.mcp_audit.classify_mcp_capabilities`), the high-risk set
(:data:`frontier_scout.safety_summary.RISKY_FLAGS`), and the finding shape
(:class:`frontier_scout.policy.PolicyFinding`).

Decision precedence is fail-closed: ``block`` if any block-class finding, else
``needs_approval`` if any approval-class finding, else ``allow``.
"""

from __future__ import annotations

import fnmatch

from frontier_scout.mcp_audit import classify_mcp_capabilities
from frontier_scout.policy import PolicyFinding
from frontier_scout.safety_summary import RISKY_FLAGS

from .models import AgentPolicy, TaskDecision, Verdict

__all__ = ["evaluate_task"]


def _normalise_path(path: str) -> str:
    """Normalise a repo-relative path for glob matching (no filesystem access)."""

    normalised = path.replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised


def _path_matches_glob(path: str, glob: str) -> bool:
    """Return True if ``path`` matches ``glob``.

    ``fnmatch`` treats ``*`` (and therefore ``**``) as matching any characters
    including ``/``, but a leading ``**/`` still requires a separator before the
    next segment — so ``**/migrations/**`` would miss a root-level
    ``migrations/x``. To approximate recursive-glob semantics without a new
    dependency, the path is tested against the glob (and its ``**/``-stripped
    form) for every trailing sub-path. Pure string work — no I/O.
    """

    normalised = _normalise_path(path)
    candidates = [glob]
    if glob.startswith("**/"):
        candidates.append(glob[3:])
    parts = normalised.split("/")
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]
    for candidate in candidates:
        for suffix in suffixes:
            if fnmatch.fnmatch(suffix, candidate):
                return True
    return False


def _looks_read_only(caps: dict[str, str], dangerous: list[str]) -> bool:
    """Heuristic: a clearly read-only task (read likely, nothing dangerous)."""

    return caps.get("read") == "likely" and not dangerous


def evaluate_task(
    task: str,
    policy: AgentPolicy,
    changed_files: list[str] | None = None,
) -> TaskDecision:
    """Evaluate a proposed agent task against ``policy``. Executes nothing.

    Returns a :class:`TaskDecision` whose ``verdict`` is ``block`` if any
    block-class rule fires, else ``needs_approval`` if any approval-class rule
    fires, else ``allow``. Fail-closed: an unclassifiable non-trivial task is
    escalated to ``needs_approval``.
    """

    files = list(changed_files or [])
    manifest = classify_mcp_capabilities(task)
    caps: dict[str, str] = dict(manifest.capabilities)
    dangerous = sorted(manifest.dangerous_flags)

    reasons: list[PolicyFinding] = []
    has_block = False
    has_approval = False

    task_lower = task.lower()
    gates = set(policy.approval_gates)

    # Block-class: explicitly blocked shell commands referenced in the task.
    for cmd in policy.blocked_shell_commands:
        if cmd and cmd.lower() in task_lower:
            reasons.append(
                PolicyFinding(
                    severity="high",
                    rule_id="shell.blocked",
                    message=f"Task references a blocked shell command: {cmd}",
                )
            )
            has_block = True

    # Block-class: explicitly blocked tools referenced in the task.
    for tool in policy.blocked_tools:
        if tool and tool.lower() in task_lower:
            reasons.append(
                PolicyFinding(
                    severity="high",
                    rule_id="tool.blocked",
                    message=f"Task references a blocked tool: {tool}",
                )
            )
            has_block = True

    # Capability gates (fail-closed): any dangerous flag in the high-risk set
    # escalates to approval. If its gate token is explicitly enabled we say so;
    # if not, we STILL require approval (a dangerous capability is never silently
    # allowed just because the policy omitted its gate).
    for flag in dangerous:
        if flag not in RISKY_FLAGS:
            continue
        if flag in gates:
            message = f"Task implies the '{flag}' capability; human approval is gated."
        else:
            message = (
                f"Task implies the '{flag}' capability; not explicitly gated — "
                "defaulting to approval (fail-closed)."
            )
        reasons.append(
            PolicyFinding(severity="medium", rule_id=f"capability.{flag}", message=message)
        )
        has_approval = True

    # Fail-closed: an unclassifiable non-trivial task needs approval.
    if (
        caps.get("unknown") == "likely"
        and task.strip()
        and not _looks_read_only(caps, dangerous)
    ):
        reasons.append(
            PolicyFinding(
                severity="medium",
                rule_id="capability.unknown",
                message="Task capability surface is unknown; review before proceeding (fail-closed).",
            )
        )
        has_approval = True

    # Protected-path changes: a proposed file change that hits a protected glob
    # needs approval (block only if it also matched a block-class rule above).
    for path in files:
        if any(_path_matches_glob(path, glob) for glob in policy.protected_file_globs):
            reasons.append(
                PolicyFinding(
                    severity="high",
                    rule_id="path.protected",
                    message=f"Proposed change touches a protected path: {path}",
                )
            )
            has_approval = True
        elif any(_path_matches_glob(path, glob) for glob in policy.allowed_file_globs):
            reasons.append(
                PolicyFinding(
                    severity="info",
                    rule_id="path.allowed",
                    message=f"Proposed change is within an allowed path: {path}",
                )
            )

    verdict: Verdict
    if has_block:
        verdict = "block"
    elif has_approval:
        verdict = "needs_approval"
    else:
        verdict = "allow"

    summary = {
        "allow": "Allowed: no blocking or approval-gated signals detected (static, advisory).",
        "needs_approval": "Needs approval: approval-gated signals detected (static, advisory).",
        "block": "Blocked: a blocked command/tool was referenced (static, advisory).",
    }[verdict]

    return TaskDecision(
        verdict=verdict,
        summary=summary,
        reasons=reasons,
        capabilities=caps,
        dangerous_flags=dangerous,
        files_considered=files,
        required_checks=list(policy.required_checks),
        warnings=[],
        static_only=True,
    )
