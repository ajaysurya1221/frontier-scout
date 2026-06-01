"""SplashScreen — the front door: the radar mark, wordmark, and one prompt.

Shown only for real launches (``run_briefing`` passes ``splash=True``); tests
construct the app without it so they land straight on Home. ``Enter`` (or any
move) opens Home; ``q`` quits.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen
from frontier_scout.tui2.widgets import Radar

_WORDMARK = "[b]F R O N T I E R[/b]  [#24d6a8]·[/]  [b]S C O U T[/b]"


class SplashScreen(BriefingScreen):
    BINDINGS = [
        Binding("enter,space", "begin", "begin", show=False),
        Binding("q", "app.quit", "quit", show=False),
    ]

    def header_text(self) -> str:
        return "◉ frontier · scout"

    def compass_text(self) -> str:
        return "⏎ begin · q quit"

    def body(self) -> Iterable[Widget]:
        yield Radar(rows=11, cols=25, classes="radar")
        yield Static(_WORDMARK, classes="hero", id="wordmark")
        yield Static("the try-before-trust radar", classes="hero-sub")
        yield Static("[#24d6a8]press ⏎ to begin[/]", classes="hero-sub")

    def action_begin(self) -> None:
        from frontier_scout.tui2.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())
