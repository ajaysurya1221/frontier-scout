"""ExploreScreen — scout anything by name or URL, no repo required.

This serves the "scout without a project" selling point: a single input that
runs an explore scout and lands on the same briefing cards.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Input, Static

from frontier_scout.tui2.screens.base import BriefingScreen


class ExploreScreen(BriefingScreen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "back", show=False),
    ]

    def compass_text(self) -> str:
        return "type a name or URL · ⏎ explore · esc back"

    def body(self) -> Iterable[Widget]:
        yield Static("Explore a tool", classes="title")
        yield Static(
            "Name a tool, library, or paste a URL. No repo needed.",
            classes="prose dim",
        )
        yield Input(placeholder="e.g. dspy, langgraph, https://github.com/...", id="query")

    def on_mount(self) -> None:
        super().on_mount()
        try:
            self.query_one("#query", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = (event.value or "").strip()
        if not query:
            return
        self.app.start_explore(query)
