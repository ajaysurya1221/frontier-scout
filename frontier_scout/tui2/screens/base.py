"""Base screen: the three-row responsive shell shared by every screen.

Layout is always Header (1) · Body (1fr, scrolls) · Compass (1). Subclasses
supply only their body content plus header/compass text — they never re-invent
the frame, so the responsive guarantee (Body fills the rest and scrolls, so
content never clips) holds for every screen by construction.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

# Below this, no layout is attempted — we show one honest line instead.
MIN_WIDTH = 24
MIN_HEIGHT = 7


class BriefingScreen(Screen):
    """A calm, single-purpose screen with a header, a body, and a compass."""

    def header_text(self) -> str:  # pragma: no cover - overridden
        app = self.app
        repo = getattr(app, "state", None)
        name = repo.repo_name if repo and repo.repo_name else "no repo"
        return f"◉ frontier · scout  ·  📁 {name}"

    def compass_text(self) -> str:  # pragma: no cover - overridden
        return "esc back · q quit"

    def body(self) -> Iterable[Widget]:  # pragma: no cover - overridden
        return ()

    def compose(self) -> ComposeResult:
        yield Static(self.header_text(), id="header")
        with VerticalScroll(id="body"):
            yield from self.body()
        yield Static(self.compass_text(), id="compass")
        yield Static("⤢  Enlarge the window", id="too-small")

    def on_mount(self) -> None:
        self._apply_floor(self.size.width, self.size.height)

    def on_resize(self) -> None:
        self._apply_floor(self.size.width, self.size.height)

    def _apply_floor(self, width: int, height: int) -> None:
        too_small = width < MIN_WIDTH or height < MIN_HEIGHT
        self.set_class(too_small, "tiny")

    # ── Helpers subclasses use to refresh the frame text in place ──────────

    def refresh_frame(self) -> None:
        """Re-render header + compass from current state (no widget reaches
        into another; each pulls from app state)."""
        try:
            self.query_one("#header", Static).update(self.header_text())
            self.query_one("#compass", Static).update(self.compass_text())
        except Exception:  # noqa: BLE001 - frame may not be mounted yet
            pass
