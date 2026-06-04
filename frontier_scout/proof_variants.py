"""A/B/C proof-variant harness for the Phase-3 validation gate.

Renders the same static safety summary three ways — approval-only, sandbox-summary, and a formal
receipt — so design partners can say which they would actually keep. The follow-up research
predicts the sandbox summary wins; this is how we test that *before* investing in behavioral
receipts. The chosen variant is captured via opt-in telemetry (``record_preference``).
"""

from __future__ import annotations

from typing import Any

from outputs._text import sanitize_sensitive_text

from .safety_summary import render_safety_summary
from .telemetry import record_event

VARIANTS = ("approval_only", "sandbox_summary", "formal_receipt")


def _approval_only(summary: dict[str, Any]) -> str:
    recommendation = "ALLOW" if summary.get("verdict") in ("adopt", "trial") else "HOLD"
    return sanitize_sensitive_text(
        f"{summary.get('tool_name', '')}: {recommendation} "
        f"(verdict {summary.get('verdict')}, risk {summary.get('risk')}). "
        f"Approve this server for the team?"
    )


def _formal_receipt(summary: dict[str, Any]) -> str:
    caps = ", ".join(key for key, status in (summary.get("capabilities") or {}).items() if status != "unlikely")
    lines = [
        "ADOPTION RECEIPT (static)",
        f"tool: {summary.get('tool_name', '')}",
        f"verdict: {summary.get('verdict')}  risk: {summary.get('risk')}  fit: {summary.get('fit')}",
        f"capabilities: {caps or 'none'}",
        f"dangerous flags: {', '.join(summary.get('dangerous_flags') or []) or 'none'}",
        f"confidence: {summary.get('confidence')}",
        "signed-by: frontier-scout (static analysis; no server execution)",
    ]
    return sanitize_sensitive_text("\n".join(lines))


def proof_variants(summary: dict[str, Any]) -> dict[str, str]:
    """Render all three proof variants for one server's static safety summary."""

    return {
        "approval_only": _approval_only(summary),
        "sandbox_summary": render_safety_summary(summary),
        "formal_receipt": _formal_receipt(summary),
    }


def record_preference(variant: str) -> bool:
    """Record which proof variant the operator kept (opt-in telemetry)."""

    if variant not in VARIANTS:
        raise ValueError(f"unknown proof variant: {variant} (choose from {', '.join(VARIANTS)})")
    return record_event("proof_variant_kept", variant=variant)
