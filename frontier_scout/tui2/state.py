"""Immutable state for the Briefing TUI (v1.5.0).

The whole app is driven by a single frozen :class:`AppState`. Every change
produces a *new* state; nothing mutates in place and no widget reaches into
another widget. This is the structural reason the Briefing can be tested to
zero bugs: there is exactly one source of truth and it is a value, not a
mutable graph of widgets.

:class:`Finding` is the view-model the cards render. It is normalised from a
raw scout verdict dict exactly once, at :meth:`Finding.from_verdict`, and the
UI never reaches past that boundary into raw dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# Verdict → one-word ribbon + tone slug. Tones map to theme colours.
_VERDICT_RIBBON: dict[str, tuple[str, str]] = {
    "adopt": ("ADOPT", "ok"),
    "trial": ("TRIAL", "info"),
    "assess": ("ASSESS", "warn"),
    "hold": ("HOLD", "muted"),
}


@dataclass(frozen=True)
class Concern:
    """One honest reservation about a tool, already classified by the backend."""

    slug: str
    label: str
    severity: str  # high | medium | low
    evidence: str

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Concern:
        return Concern(
            slug=str(raw.get("slug") or ""),
            label=str(raw.get("label") or raw.get("slug") or "concern"),
            severity=str(raw.get("severity") or "low").lower(),
            evidence=str(raw.get("evidence") or ""),
        )


@dataclass(frozen=True)
class Finding:
    """A single briefing card, normalised from a scout verdict.

    This is a *pure* projection of a verdict dict: same input always yields the
    same Finding (see ``tests/test_tui2.py::test_finding_from_verdict_is_pure``).
    """

    tool_name: str
    verdict: str  # adopt | trial | assess | hold
    fit: str  # high | medium | low | ""
    risk: str
    category: str
    summary: str
    why_fit: str
    next_step: str
    url: str
    concerns: tuple[Concern, ...] = ()

    # ── Derived display helpers (no I/O, pure) ──────────────────────────────

    @property
    def ribbon(self) -> str:
        return _VERDICT_RIBBON.get(self.verdict.lower(), ("SCOUTED", "muted"))[0]

    @property
    def ribbon_tone(self) -> str:
        return _VERDICT_RIBBON.get(self.verdict.lower(), ("SCOUTED", "muted"))[1]

    @property
    def top_severity(self) -> str:
        """Highest-severity concern level, or '' when there are none."""
        order = {"high": 3, "medium": 2, "low": 1}
        if not self.concerns:
            return ""
        return max(self.concerns, key=lambda c: order.get(c.severity, 0)).severity

    @staticmethod
    def from_verdict(raw: dict[str, Any]) -> Finding:
        """Normalise a (possibly personalised) verdict dict into a Finding.

        Tolerant of missing keys — every field has a sensible default so a
        partial verdict never crashes a card.
        """
        fit_reasons = raw.get("fit_reasons") or []
        why_fit = "; ".join(str(r) for r in fit_reasons) if fit_reasons else ""
        concerns = tuple(
            Concern.from_dict(c) for c in (raw.get("concerns") or []) if isinstance(c, dict)
        )
        return Finding(
            tool_name=str(raw.get("tool_name") or "unknown"),
            verdict=str(raw.get("verdict") or "assess").lower(),
            fit=str(raw.get("fit") or "").lower(),
            risk=str(raw.get("risk") or "").lower(),
            category=str(raw.get("category") or ""),
            summary=str(raw.get("what") or raw.get("why_it_matters") or ""),
            why_fit=why_fit,
            next_step=str(raw.get("next_safe_step") or raw.get("next_action") or ""),
            url=str(raw.get("source_url") or raw.get("release_url") or ""),
            concerns=concerns,
        )


@dataclass(frozen=True)
class AppState:
    """The single source of truth for the Briefing app.

    Immutable: use :meth:`with_` to produce a changed copy. Widgets read from
    this; they never write to each other.
    """

    repo: str = ""
    repo_name: str = ""
    has_repo: bool = False
    findings: tuple[Finding, ...] = ()
    cursor: int = 0  # index into findings on the FindingsScreen carousel
    provider: str = ""  # resolved provider name, or "" when none
    dismissed: frozenset[str] = field(default_factory=frozenset)

    def with_(self, **changes: Any) -> AppState:
        """Return a new AppState with the given fields replaced."""
        return replace(self, **changes)

    # ── Carousel helpers (pure, always in-range) ────────────────────────────

    @property
    def current(self) -> Finding | None:
        if not self.findings:
            return None
        return self.findings[self._clamp(self.cursor)]

    def _clamp(self, idx: int) -> int:
        if not self.findings:
            return 0
        return max(0, min(idx, len(self.findings) - 1))

    def at(self, idx: int) -> AppState:
        return self.with_(cursor=self._clamp(idx))

    def next_card(self) -> AppState:
        return self.at(self.cursor + 1)

    def prev_card(self) -> AppState:
        return self.at(self.cursor - 1)

    def visible_findings(self) -> tuple[Finding, ...]:
        """Findings minus any the user has dismissed (and remembered)."""
        return tuple(f for f in self.findings if f.tool_name not in self.dismissed)
