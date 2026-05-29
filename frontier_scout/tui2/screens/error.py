"""ErrorScreen — errors are a screen, not an exception.

Any worker failure routes here: what happened · what to try · Esc back. The UI
can never crash to a frozen panel because every worker exception is caught at
the bridge and turned into one of these.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen


class ErrorScreen(BriefingScreen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back", show=False),
        Binding("enter", "app.pop_screen", "back", show=False),
    ]

    def __init__(self, message: str, suggestion: str = "") -> None:
        super().__init__()
        self._message = message
        self._suggestion = suggestion

    def compass_text(self) -> str:
        return "esc back · q quit"

    def body(self) -> Iterable[Widget]:
        yield Static("  Something went wrong", classes="ribbon-warn card")
        yield Static(self._message or "Unknown error.", classes="prose")
        if self._suggestion:
            yield Static(f"[b]Try this[/b]\n{self._suggestion}", classes="prose")
        yield Static("[dim]esc — go back[/dim]", classes="prose")
