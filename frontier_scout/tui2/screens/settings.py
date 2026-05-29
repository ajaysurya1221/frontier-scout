"""SettingsScreen — calm, read-mostly: providers, memory, version.

Provider availability dots, clear-memory actions (this repo / all), and version
+ paths. Each action shows a one-line confirmation inline so a click visibly
lands.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen


class SettingsScreen(BriefingScreen):
    BINDINGS = [
        Binding("down,j", "move(1)", "down", show=False),
        Binding("up,k", "move(-1)", "up", show=False),
        Binding("enter", "choose", "choose", show=False),
        Binding("escape", "app.pop_screen", "back", show=False),
    ]

    _ACTIONS = (
        ("clear_repo", "Clear memory for this repo"),
        ("clear_all", "Clear all memory"),
    )

    def __init__(self) -> None:
        super().__init__()
        self._sel = 0

    def compass_text(self) -> str:
        return "↑↓ move · ⏎ run · esc back"

    def body(self) -> Iterable[Widget]:
        yield Static("Settings", classes="title")
        yield Static(self._providers_block(), classes="prose")
        yield Static(self._version_block(), classes="prose dim")
        yield Static("[b]Memory[/b]", classes="prose")
        for i, (_key, label) in enumerate(self._ACTIONS):
            yield Static(self._row(i, label), classes="menu-row", id=f"set-{i}")
        yield Static("", id="set-status", classes="prose dim")

    def _providers_block(self) -> str:
        try:
            from frontier_scout.providers import PROVIDER_NAMES, available_providers

            avail = set(available_providers())
            lines = ["[b]Providers[/b]"]
            for name in PROVIDER_NAMES:
                dot = "[green]●[/green]" if name in avail else "[dim]○[/dim]"
                state = "available" if name in avail else "not configured"
                lines.append(f"  {dot} {name} — {state}")
            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            return "[b]Providers[/b]\n  (unavailable)"

    def _version_block(self) -> str:
        try:
            from frontier_scout import __version__
            from frontier_scout.store import home_dir

            return f"frontier-scout v{__version__}\nstate: {home_dir()}"
        except Exception:  # noqa: BLE001
            return ""

    def _row(self, i: int, label: str) -> str:
        marker = "▸" if i == self._sel else " "
        text = f"{marker} {label}"
        return f"[b]{text}[/b]" if i == self._sel else text

    def _refresh_rows(self) -> None:
        for i, (_key, label) in enumerate(self._ACTIONS):
            self.query_one(f"#set-{i}", Static).update(self._row(i, label))

    def action_move(self, delta: int) -> None:
        self._sel = (self._sel + delta) % len(self._ACTIONS)
        self._refresh_rows()

    def action_choose(self) -> None:
        key = self._ACTIONS[self._sel][0]
        msg = self.app.run_settings_action(key)
        try:
            self.query_one("#set-status", Static).update(f"[green]{msg}[/green]")
        except Exception:  # noqa: BLE001
            pass
