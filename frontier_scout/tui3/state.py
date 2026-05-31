"""Mission Control (tui3) — immutable view-model.

Frozen dataclasses projected from the real backend payloads (scout.run_scan,
scheduling, store, packs, …). The screens read this state and never mutate it;
the app controller produces new state with ``with_(...)``. This mirrors the
Briefing's (tui2) proven state model and keeps redraws deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Concern:
    label: str
    severity: str  # high | medium | low
    evidence: str


@dataclass(frozen=True)
class Verdict:
    tool_name: str
    verdict: str            # adopt | trial | assess | hold
    fit: str                # high | medium | low
    risk: str               # high | medium | low
    category: str
    source_url: str
    what: str               # one-line summary
    why_it_matters: str
    fit_reasons: tuple[str, ...]
    concerns: tuple[Concern, ...]
    next_safe_step: str
    unknowns: tuple[str, ...] = ()
    kind: str = "tool"      # tool | dep
    age: str = ""
    pack: str = ""
    # dependency-only
    from_version: str = ""
    to_version: str = ""
    classification: str = ""

    @property
    def source(self) -> str:
        """Short source host, e.g. github / pypi / huggingface."""
        url = self.source_url or ""
        for host, label in (
            ("github.com", "github"), ("pypi.org", "pypi"),
            ("huggingface.co", "huggingface"), ("npmjs", "npm"),
        ):
            if host in url:
                return label
        return "web"

    @classmethod
    def from_payload(cls, d: dict[str, Any], *, kind: str = "tool") -> Verdict:
        concerns = tuple(
            Concern(
                label=str(c.get("label", c.get("slug", "concern"))),
                severity=str(c.get("severity", "low")),
                evidence=str(c.get("evidence", "")),
            )
            for c in (d.get("concerns") or [])
            if isinstance(c, dict)
        )
        return cls(
            tool_name=str(d.get("tool_name", "—")),
            verdict=str(d.get("verdict", "assess")),
            fit=str(d.get("fit", "medium")),
            risk=str(d.get("risk", "medium")),
            category=str(d.get("category", "")),
            source_url=str(d.get("source_url", "")),
            what=str(d.get("what", d.get("summary", ""))),
            why_it_matters=str(d.get("why_it_matters", "")),
            fit_reasons=tuple(str(x) for x in (d.get("fit_reasons") or [])),
            concerns=concerns,
            next_safe_step=str(d.get("next_safe_step", "")),
            unknowns=tuple(str(x) for x in (d.get("unknowns") or [])),
            kind=kind,
            age=str(d.get("age", "")),
            pack=str(d.get("pack", "")),
            from_version=str(d.get("from_version", "")),
            to_version=str(d.get("to_version", "")),
            classification=str(d.get("classification", "")),
        )


@dataclass(frozen=True)
class Funnel:
    scanned: int = 0
    candidates: int = 0
    verdicts: int = 0
    cost: float = 0.0
    duration: float = 0.0
    last_run: str = "never"
    window: str = "last 7 days"

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> Funnel:
        return cls(
            scanned=int(p.get("scanned", 0) or 0),
            candidates=int(p.get("candidates", 0) or 0),
            verdicts=len(p.get("verdicts") or []),
            cost=float(p.get("cost_usd", 0.0) or 0.0),
            duration=float(p.get("duration_s", 0.0) or 0.0),
            last_run=str(p.get("date", "never") or "never"),
        )


@dataclass(frozen=True)
class AppState:
    repo: str = "."
    repo_name: str = "."
    languages: tuple[str, ...] = ()
    provider: str = "local"
    verdicts: tuple[Verdict, ...] = ()
    funnel: Funnel = field(default_factory=Funnel)
    tab: str = "scout"          # active tab id
    sel: int = 0                # selected verdict index
    scope: str = "all"          # all | ai-devtools | mcp | deps
    unicode: bool = True
    color: bool = True
    demo: bool = False
    unread: int = 0

    def with_(self, **kw: Any) -> AppState:
        return replace(self, **kw)

    @property
    def current(self) -> Verdict | None:
        if not self.verdicts:
            return None
        i = max(0, min(self.sel, len(self.verdicts) - 1))
        return self.verdicts[i]

    @property
    def scoped_verdicts(self) -> tuple[Verdict, ...]:
        if self.scope == "all":
            return self.verdicts
        if self.scope == "deps":
            return tuple(v for v in self.verdicts if v.kind == "dep")
        return tuple(v for v in self.verdicts if v.pack == self.scope)

    def move(self, delta: int) -> AppState:
        n = len(self.scoped_verdicts)
        if n == 0:
            return self
        return self.with_(sel=max(0, min(n - 1, self.sel + delta)))
