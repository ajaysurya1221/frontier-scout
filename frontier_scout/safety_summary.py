"""Static safety summary for an MCP server: capability map + policy read, no execution.

This is the MVP "proof" the pivot ships. It is deterministic and offline — it derives a
permission map from the server's name/description/tags (``mcp_audit``) and a policy verdict
(``policy``) **without starting the server or running anything**. Behavioral sandbox evidence is
a separate, gated V1 build (see ``docs/spike-mcp-probe.md``).
"""

from __future__ import annotations

from typing import Any

from outputs._text import sanitize_sensitive_text

from .evaluate import evaluate_url
from .packs import PackCandidate
from .policy import Policy, evaluate_policy

# Capability flags that gate sanction behind explicit human review (static analysis only;
# per the verification-gap demand signal: scrutiny for selected high-risk tools).
RISKY_FLAGS = frozenset({"write", "shell", "credential", "network"})


def build_safety_summary(
    candidate: PackCandidate,
    *,
    stack: dict[str, Any] | None = None,
    policy: Policy | None = None,
) -> dict[str, Any]:
    """Compute a STATIC safety map for a server: capabilities + a policy verdict.

    Nothing is executed — deterministic static analysis from local text only.
    """

    stack = stack or {}
    url = str(candidate.server_meta.get("url") or "").strip() or f"mcp://{candidate.tool_name}"
    # Capabilities come from the human description + tags only — NOT from server_meta,
    # whose config keys (``command``, ``args``, ``url``) would falsely trip the shell/
    # network capability patterns.
    source_text = " ".join(part for part in (candidate.description, " ".join(candidate.tags)) if part)
    evaluation = evaluate_url(url, stack, source_text=source_text)
    manifest = evaluation.permission_manifest
    decision = evaluate_policy(evaluation, manifest, None, policy=policy)
    dangerous = list(manifest.dangerous_flags) if manifest else ["unknown"]
    summary = {
        "tool_name": candidate.tool_name,
        "kind": "static",
        "description": sanitize_sensitive_text(candidate.description),
        "category": evaluation.category,
        "fit": evaluation.fit,
        "risk": evaluation.risk,
        "source_trust": evaluation.source_trust,
        "capabilities": dict(manifest.capabilities) if manifest else {},
        "dangerous_flags": dangerous,
        "confidence": manifest.confidence if manifest else "low",
        "verdict": decision.verdict,
        "policy_summary": sanitize_sensitive_text(decision.summary),
        "findings": [{**f.model_dump(), "message": sanitize_sensitive_text(f.message)} for f in decision.findings],
    }
    summary["requires_review"] = is_high_risk(summary)  # single source of truth
    return summary


def is_high_risk(summary: dict[str, Any]) -> bool:
    """True when the server has a capability flag that should gate sanction behind review."""

    return bool(RISKY_FLAGS.intersection(summary.get("dangerous_flags") or []))


def render_safety_summary(summary: dict[str, Any]) -> str:
    """Render the static safety map as redacted markdown (no secrets leak)."""

    caps = summary.get("capabilities") or {}
    cap_lines = [f"- `{key}`: {status}" for key, status in caps.items() if status != "unlikely"] or [
        "- (no capabilities classified)"
    ]
    flags = summary.get("dangerous_flags") or []
    findings = summary.get("findings") or []
    finding_lines = [f"- [{f.get('severity')}] {f.get('rule_id')}: {f.get('message')}" for f in findings] or [
        "- (no policy findings)"
    ]
    lines = [
        f"## Static safety analysis — {summary.get('tool_name', '')}",
        "",
        "_Static analysis only — no server was started or executed._",
        "",
        f"**Verdict:** {summary.get('verdict', '?')} · fit {summary.get('fit')} · "
        f"risk {summary.get('risk')} · source trust {summary.get('source_trust')} · "
        f"confidence {summary.get('confidence')}",
        f"> {summary.get('policy_summary', '')}",
        "",
        f"Description: {summary.get('description') or '(none)'}",
        "",
        "### Capability map",
        *cap_lines,
        "",
        f"Dangerous flags: {', '.join(flags) if flags else 'none'}",
        "",
        "### Policy findings",
        *finding_lines,
    ]
    return sanitize_sensitive_text("\n".join(lines))
