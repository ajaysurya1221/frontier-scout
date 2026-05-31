"""HomeScreen — the calm menu. One focused choice at a time."""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen
from frontier_scout.tui2.widgets import Radar

# (key, label, hint) — order is the on-screen order.
_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("scout", "Scout my repo", "newest AI tools that fit this code"),
    ("explore", "Explore a tool", "ask about anything, no repo needed"),
    ("settings", "Settings", "providers, memory, version"),
    ("quit", "Quit", ""),
)


class HomeScreen(BriefingScreen):
    BINDINGS = [
        Binding("down,j", "move(1)", "down", show=False),
        Binding("up,k", "move(-1)", "up", show=False),
        Binding("enter", "choose", "choose", show=False),
        Binding("q", "app.quit", "quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sel = 0

    def header_text(self) -> str:
        name = self.app.state.repo_name or "no repo"
        return f"◉ frontier · scout  ·  📁 {name}"

    def compass_text(self) -> str:
        return "↑↓ move · ⏎ choose · q quit"

    def body(self) -> Iterable[Widget]:
        yield Static(f"[#24d6a8]{self._kicker()}[/]", classes="kicker", id="kicker")
        yield Radar(rows=9, cols=21, classes="radar")
        yield Static("What would you like to do?", classes="title")
        for i, (_key, label, hint) in enumerate(_ITEMS):
            yield Static(
                self._row(i, label, hint),
                classes="menu-row" + (" sel" if i == self._sel else ""),
                id=f"item-{i}",
            )

    def _kicker(self) -> str:
        return f"◉ {self.app.provider_label()} · ready"

    def _row(self, i: int, label: str, hint: str) -> str:
        marker = "▸" if i == self._sel else " "
        text = f"{marker} {label}"
        if hint:
            text = f"{text}".ljust(22) + f"[dim]{hint}[/dim]"
        return text

    def _refresh_rows(self) -> None:
        for i, (_key, label, hint) in enumerate(_ITEMS):
            row = self.query_one(f"#item-{i}", Static)
            row.update(self._row(i, label, hint))
            row.set_class(i == self._sel, "sel")

    def action_move(self, delta: int) -> None:
        self._sel = (self._sel + delta) % len(_ITEMS)
        self._refresh_rows()

    def action_choose(self) -> None:
        key = _ITEMS[self._sel][0]
        if key == "scout":
            self.app.start_scout()
        elif key == "explore":
            from frontier_scout.tui2.screens.explore import ExploreScreen

            self.app.push_screen(ExploreScreen())
        elif key == "settings":
            from frontier_scout.tui2.screens.settings import SettingsScreen

            self.app.push_screen(SettingsScreen())
        elif key == "quit":
            self.app.exit()
