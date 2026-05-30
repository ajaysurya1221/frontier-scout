"""ActionsMenu — the small "more actions" list opened with `a` from a card."""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen
from frontier_scout.tui2.state import Finding


class ActionsMenu(BriefingScreen):
    BINDINGS = [
        Binding("down,j", "move(1)", "down", show=False),
        Binding("up,k", "move(-1)", "up", show=False),
        Binding("enter", "choose", "choose", show=False),
        Binding("escape", "app.pop_screen", "back", show=False),
    ]

    def __init__(self, finding: Finding) -> None:
        super().__init__()
        self._finding = finding
        self._sel = 0
        self._items: list[tuple[str, str]] = []

    def _build_items(self) -> list[tuple[str, str]]:
        primary = (
            ("implement", "Implement & test")
            if self.app.state.has_repo
            else ("explain", "Tell me more (fit + security)")
        )
        items = [primary, ("lab", "Lab it (hermetic probe)"), ("dismiss", "Dismiss & remember")]
        if self._finding.url:
            items.append(("open", "Open URL"))
        return items

    def compass_text(self) -> str:
        return "↑↓ move · ⏎ choose · esc back"

    def body(self) -> Iterable[Widget]:
        self._items = self._build_items()
        yield Static(f"Actions · {self._finding.tool_name}", classes="title")
        for i, (_key, label) in enumerate(self._items):
            yield Static(
                self._row(i, label),
                classes="menu-row" + (" sel" if i == self._sel else ""),
                id=f"act-{i}",
            )

    def _row(self, i: int, label: str) -> str:
        marker = "▸" if i == self._sel else " "
        return f"{marker} {label}"

    def _refresh_rows(self) -> None:
        for i, (_key, label) in enumerate(self._items):
            row = self.query_one(f"#act-{i}", Static)
            row.update(self._row(i, label))
            row.set_class(i == self._sel, "sel")

    def action_move(self, delta: int) -> None:
        if not self._items:
            return
        self._sel = (self._sel + delta) % len(self._items)
        self._refresh_rows()

    def action_choose(self) -> None:
        if not self._items:
            return
        key = self._items[self._sel][0]
        self.app.pop_screen()  # close the menu first
        if key == "implement":
            self.app.start_implement(self._finding)
        elif key == "explain":
            self.app.start_explain(self._finding)
        elif key == "lab":
            self.app.start_lab(self._finding)
        elif key == "dismiss":
            self.app.dismiss_finding(self._finding.tool_name)
        elif key == "open" and self._finding.url:
            import webbrowser
            from urllib.parse import urlparse

            try:
                # Only open http(s) links — never file://, javascript:, etc.
                if urlparse(self._finding.url).scheme in {"http", "https"}:
                    webbrowser.open(self._finding.url)
            except Exception:  # noqa: BLE001
                pass
