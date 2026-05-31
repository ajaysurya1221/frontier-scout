"""WorkingScreen — calm staged progress. Never looks frozen, always cancellable.

Fed by ``Progress`` messages from a worker via :class:`TuiReporter`. Shows the
current stage with a spinner, completed stages dimmed with ✓, and an elapsed
timer. ``Esc`` cancels the worker and returns home. Because the worker always
ends in a terminal message, this screen always gives way to a result or error
screen — it can never wait forever.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.messages import Progress
from frontier_scout.tui2.screens.base import BriefingScreen
from frontier_scout.tui2.widgets import Radar

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class WorkingScreen(BriefingScreen):
    BINDINGS = [
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self, title: str = "Working…") -> None:
        super().__init__()
        self._title = title
        self._stages: list[tuple[str, bool]] = []  # (label, done)
        self._started = time.monotonic()
        self._tick = 0

    def compass_text(self) -> str:
        return "esc to cancel"

    def body(self) -> Iterable[Widget]:
        yield Radar(rows=13, cols=29, classes="radar")
        yield Static(self._title, classes="title")
        yield Static("Starting…", id="stages", classes="prose")
        yield Static("0s elapsed", id="elapsed", classes="prose dim")

    def on_mount(self) -> None:
        super().on_mount()
        self.set_interval(0.1, self._animate)

    def _animate(self) -> None:
        self._tick += 1
        self._render_stages()
        elapsed = int(time.monotonic() - self._started)
        try:
            self.query_one("#elapsed", Static).update(f"{elapsed}s elapsed")
        except Exception:  # noqa: BLE001
            pass

    def _render_stages(self) -> None:
        if not self._stages:
            return
        spin = _SPINNER[self._tick % len(_SPINNER)]
        lines: list[str] = []
        for label, done in self._stages:
            if done:
                lines.append(f"[dim]✓ {label}[/dim]")
            else:
                lines.append(f"{spin} {label}")
        try:
            self.query_one("#stages", Static).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    def apply_progress(self, msg: Progress) -> None:
        """Called by the app when a Progress message arrives for this screen."""
        if msg.done:
            self._stages = [(label, True if label == msg.stage else d) for label, d in self._stages]
            return
        # New stage: mark all prior as done, append the new one as active.
        if not any(label == msg.stage for label, _ in self._stages):
            self._stages = [(label, True) for label, _ in self._stages]
            self._stages.append((msg.stage, False))
        self._render_stages()

    def action_cancel(self) -> None:
        self.app.cancel_work()
