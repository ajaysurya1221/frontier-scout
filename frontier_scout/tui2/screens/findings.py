"""FindingsScreen — the briefing. One Finding per screen as a card.

``←/→`` (and ``h/l``) flip cards; a dot-trail shows position. ``Enter`` runs
the context-primary action (Implement & test with a repo, Tell me more without
one); ``a`` opens more actions; ``o`` opens the URL; ``d`` dismisses; ``Esc``
home. The carousel index is held in immutable AppState and is always clamped
in range, so the ends never overshoot.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen
from frontier_scout.tui2.state import Finding

# Filled verdict pill: (foreground, background) per ribbon tone, from the design.
_PILL: dict[str, tuple[str, str]] = {
    "ok": ("#06231b", "#24d6a8"),
    "info": ("#091a36", "#7aa6ff"),
    "warn": ("#2b2208", "#e3c26f"),
    "muted": ("#d9f7ff", "#25405c"),
}
# Concern severity → colour.
_SEV_COLOR = {"high": "#ff6b6b", "medium": "#e3c26f", "low": "#6e8aa1"}


def _pill(finding: Finding) -> str:
    fg, bg = _PILL.get(finding.ribbon_tone, _PILL["muted"])
    return f"[{fg} on {bg}] {finding.ribbon} [/]"


def card_widgets(finding: Finding, index: int, total: int, has_repo: bool) -> list[Widget]:
    """Pure: build the Static widgets for one briefing card."""
    meta = []
    if finding.fit:
        meta.append(f"fit [b]{finding.fit}[/b]")
    if finding.risk:
        meta.append(f"risk [b]{finding.risk}[/b]")
    if finding.category:
        meta.append(finding.category)
    ribbon_line = _pill(finding)
    if meta:
        ribbon_line += "   [dim]" + "  ·  ".join(meta) + "[/dim]"

    widgets: list[Widget] = [
        Static(ribbon_line, classes="ribbon"),
        Static(finding.tool_name, classes="title"),
    ]
    if finding.summary:
        widgets.append(Static(finding.summary, classes="prose"))
    if finding.why_fit:
        widgets.append(Static("WHY IT FITS YOUR REPO", classes="block-h"))
        bullets = "\n".join(f"[#24d6a8]›[/] {r.strip()}" for r in finding.why_fit.split(";") if r.strip())
        widgets.append(Static(bullets, classes="prose"))
    if finding.concerns:
        widgets.append(Static("CONCERNS", classes="block-h"))
        for c in finding.concerns:
            color = _SEV_COLOR.get(c.severity, "#6e8aa1")
            line = f"[{color}]●[/] [b]{c.label}[/b] [dim]{c.severity}[/dim]"
            if c.evidence:
                line += f"\n  [dim]{c.evidence}[/dim]"
            widgets.append(Static(line, classes="prose"))
    else:
        widgets.append(Static("[dim]✓ No concerns flagged.[/dim]", classes="prose"))
    if finding.next_step:
        widgets.append(Static("NEXT SAFE STEP", classes="block-h"))
        widgets.append(Static(finding.next_step, classes="next-step"))

    primary = "Implement & test" if has_repo else "Tell me more"
    widgets.append(
        Static(
            f"[dim]⏎ {primary}   ·   a more   ·   o open   ·   d dismiss[/dim]",
            classes="prose",
        )
    )

    dots = " ".join("[#24d6a8]●[/]" if i == index else "[dim]○[/dim]" for i in range(total))
    widgets.append(Static(f"{dots}   [dim]({index + 1}/{total})[/dim]", classes="dots"))
    return widgets


class FindingsScreen(BriefingScreen):
    BINDINGS = [
        Binding("right,l", "nav(1)", "next", show=False),
        Binding("left,h", "nav(-1)", "prev", show=False),
        Binding("enter", "primary", "do", show=False),
        Binding("a", "more", "more", show=False),
        Binding("o", "open_url", "open", show=False),
        Binding("d", "dismiss", "dismiss", show=False),
        Binding("escape", "home", "home", show=False),
    ]

    def compass_text(self) -> str:
        if not self.app.state.visible_findings():
            return "esc home · q quit"
        primary = "implement" if self.app.state.has_repo else "tell me more"
        return f"←/→ flip · ⏎ {primary} · a more · o open · d dismiss · esc home"

    def _findings(self) -> tuple[Finding, ...]:
        return self.app.state.visible_findings()

    def body(self) -> Iterable[Widget]:
        yield from self._card()

    def _card(self) -> list[Widget]:
        findings = self._findings()
        if not findings:
            return [
                Static("No findings", classes="title"),
                Static("Nothing to brief right now. Press esc to go home.", classes="prose dim"),
            ]
        idx = max(0, min(self.app.state.cursor, len(findings) - 1))
        return card_widgets(findings[idx], idx, len(findings), self.app.state.has_repo)

    async def _rerender(self) -> None:
        body = self.query_one("#body", VerticalScroll)
        await body.remove_children()
        await body.mount(*self._card())
        self.refresh_frame()

    async def action_nav(self, delta: int) -> None:
        self.app.state = self.app.state.at(self.app.state.cursor + delta)
        await self._rerender()

    def _current(self) -> Finding | None:
        findings = self._findings()
        if not findings:
            return None
        idx = max(0, min(self.app.state.cursor, len(findings) - 1))
        return findings[idx]

    def action_primary(self) -> None:
        finding = self._current()
        if finding is None:
            return
        if self.app.state.has_repo:
            self.app.start_implement(finding)
        else:
            self.app.start_explain(finding)

    def action_more(self) -> None:
        finding = self._current()
        if finding is None:
            return
        from frontier_scout.tui2.screens.actions_menu import ActionsMenu

        self.app.push_screen(ActionsMenu(finding))

    def action_open_url(self) -> None:
        finding = self._current()
        if finding and finding.url:
            import webbrowser
            from urllib.parse import urlparse

            try:
                # Only open http(s) links — never file://, javascript:, etc.
                if urlparse(finding.url).scheme in {"http", "https"}:
                    webbrowser.open(finding.url)
            except Exception:  # noqa: BLE001
                pass

    async def action_dismiss(self) -> None:
        finding = self._current()
        if finding is None:
            return
        self.app.dismiss_finding(finding.tool_name)
        await self._rerender()

    def action_home(self) -> None:
        self.app.pop_screen()
