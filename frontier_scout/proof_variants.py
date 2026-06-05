"""A/B/C proof-variant harness for the Phase-3 validation gate.

Renders the same static safety summary three ways — approval-only, static-safety-summary, and a
formal (generated, static) assessment — so design partners can say which they would actually keep.
The follow-up research predicts the static safety summary wins; this is how we test that *before*
investing in any behavioral evidence. Every variant is static analysis only — nothing is executed.
The chosen variant is captured via opt-in telemetry (``record_preference``).
"""

from __future__ import annotations

from typing import Any

from outputs._text import sanitize_sensitive_text

from .safety_summary import render_safety_summary
from .telemetry import record_event

VARIANTS = ("approval_only", "static_safety_summary", "formal_receipt")

# Legacy names normalized on the way in so no misleading "sandbox" label is recorded/shown.
_LEGACY_VARIANT_ALIASES = {"sandbox_summary": "static_safety_summary"}


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
        "STATIC ADOPTION ASSESSMENT",
        f"tool: {summary.get('tool_name', '')}",
        f"verdict: {summary.get('verdict')}  risk: {summary.get('risk')}  fit: {summary.get('fit')}",
        f"capabilities: {caps or 'none'}",
        f"dangerous flags: {', '.join(summary.get('dangerous_flags') or []) or 'none'}",
        f"confidence: {summary.get('confidence')}",
        "generated-by: frontier-scout (static analysis; no server executed)",
    ]
    return sanitize_sensitive_text("\n".join(lines))


def proof_variants(summary: dict[str, Any]) -> dict[str, str]:
    """Render all three proof variants for one server's static safety summary."""

    return {
        "approval_only": _approval_only(summary),
        "static_safety_summary": render_safety_summary(summary),
        "formal_receipt": _formal_receipt(summary),
    }


def record_preference(variant: str) -> bool:
    """Record which proof variant the operator kept (opt-in telemetry)."""

    variant = _LEGACY_VARIANT_ALIASES.get(variant, variant)
    if variant not in VARIANTS:
        raise ValueError(f"unknown proof variant: {variant} (choose from {', '.join(VARIANTS)})")
    return record_event("proof_variant_kept", variant=variant)
