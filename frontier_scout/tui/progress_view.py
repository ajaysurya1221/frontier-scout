"""v1.3.0 — TUI sinks for `frontier_scout.progress.ProgressReporter`.

Backends (workers in @work threads, subprocess wrappers, etc.) call
``reporter.stage / advance / log`` without knowing the TUI exists.

This module provides:

- ``StatusStrip(Static)`` — a one-row widget that renders the running
  stage list as ``● Current  ✓ Done  ○ Pending`` with a Braille
  spinner. Always visible.
- ``ProgressStrip(ProgressBar)`` — a Textual progress bar that becomes
  visible only while a worker is reporting fractions; hides when idle.
- ``TuiProgressReporter`` — the concrete ``ProgressReporter`` the
  shell hands out to action handlers. It marshals every call back to
  the Textual loop via ``call_from_thread`` so threaded workers stay
  safe.

The activity log sink is just the existing ``app.log_event`` channel
from v1.2.1 — we don't introduce a new widget.

Design constraint: at narrow widths (< 90 cols) only the spinner +
current stage label remain visible; the past-stage trail and the
counter collapse. The progress bar hides entirely. This makes the
status row safe on a VS Code 80×24 panel.
"""

from __future__ import annotations

from itertools import cycle

from textual.reactive import reactive
from textual.widgets import ProgressBar, Static

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class StatusStrip(Static):
    """One-row status display: spinner + stage trail + counter.

    Rendered as a single Static — no inner widgets — so the rendering
    pipeline is bulletproof. The spinner ticks on a 6Hz interval.

    Reactive state:
        - ``current``: the in-flight stage label (empty = idle).
        - ``stages_done``: ordered list of completed stage labels.
        - ``total_stages``: optional total for rendering ``2/4``.
    """

    DEFAULT_CSS = """
    StatusStrip {
        height: 1;
        background: #0d1622;
        padding: 0 2;
        color: #d9f7ff;
    }
    """

    current: reactive[str] = reactive("")
    stages_done: reactive[list[str]] = reactive(list)
    total_stages: reactive[int | None] = reactive(None)
    idle_message: reactive[str] = reactive("Ready")
    narrow: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__("[#6e8aa1]Ready[/]", markup=True)
        self._frames = cycle(_SPINNER_FRAMES)

    def on_mount(self) -> None:
        # Animate the spinner ~6Hz; cheap, doesn't pull on the worker.
        self.set_interval(1 / 6, self._tick)
        self._refresh_label()

    def _tick(self) -> None:
        self._refresh_label()

    def _refresh_label(self) -> None:
        # NB: do NOT name this ``_render`` — that's a private hook on
        # Static and overriding it silently returns None, which crashes
        # the rendering pipeline downstream.
        if not self.current:
            self.update(f"[#6e8aa1]{self.idle_message}[/]")
            return
        spinner = next(self._frames)
        counter = ""
        if self.total_stages:
            done = len(self.stages_done) + 1
            counter = f" [#6e8aa1]{done}/{self.total_stages}[/]"
        if self.narrow:
            # Narrow: just spinner + current stage + counter.
            self.update(f"[#24d6a8]{spinner}[/] [#d9f7ff]{self.current}[/]{counter}")
            return
        # Wide: include the trail.
        trail_parts = [f"[#24d6a8]✓ {s}[/]" for s in self.stages_done[-3:]]
        trail = "  ".join(trail_parts)
        if trail:
            trail = f"{trail}  "
        self.update(
            f"{trail}[#e3c26f]{spinner}[/] [#d9f7ff bold]{self.current}[/]{counter}"
        )

    # ------------------------------------------------------------------
    # Public API — called by TuiProgressReporter on the main loop
    # ------------------------------------------------------------------

    def start_stage(self, label: str, total_stages: int | None) -> None:
        # If a previous stage was running, mark it done.
        if self.current:
            self.stages_done = [*self.stages_done, self.current]
        self.current = label
        if total_stages is not None:
            self.total_stages = total_stages
        self._refresh_label()

    def finish_all(self, summary: str | None = None) -> None:
        if self.current:
            self.stages_done = [*self.stages_done, self.current]
        self.current = ""
        self.idle_message = summary or "Ready"
        # Trim trail so the next run doesn't show stale checks.
        self.stages_done = []
        self.total_stages = None
        self._refresh_label()


class ProgressStrip(ProgressBar):
    """ProgressBar that only shows while a worker is reporting fractions."""

    DEFAULT_CSS = """
    ProgressStrip {
        height: 1;
        background: #0d1622;
        padding: 0 2;
    }

    ProgressStrip.hidden {
        display: none;
    }
    """

    def on_mount(self) -> None:
        self.add_class("hidden")
        self.update(total=100, progress=0)

    def show(self) -> None:
        self.remove_class("hidden")

    def hide(self) -> None:
        self.add_class("hidden")
        self.update(total=100, progress=0)

    def set_fraction(self, fraction: float) -> None:
        f = max(0.0, min(1.0, float(fraction)))
        self.show()
        self.update(progress=int(round(f * 100)))


class TuiProgressReporter:
    """ProgressReporter implementation that fans out to TUI sinks.

    Each method marshals to the Textual loop via ``call_from_thread``
    so workers can call it from any thread without crashing the UI.
    The reporter holds *weak-ish* references to widgets — if a sink
    isn't mounted yet, the call silently drops. This keeps the
    reporter usable during shell startup.
    """

    def __init__(
        self,
        *,
        app,  # noqa: ANN001 — Textual App; avoid hard dep at import time
        status: StatusStrip | None = None,
        bar: ProgressStrip | None = None,
        log_event=None,  # noqa: ANN001 — callable(str, str)
    ) -> None:
        self._app = app
        self._status = status
        self._bar = bar
        self._log_event = log_event

    # ------------------------------------------------------------------
    # ProgressReporter protocol
    # ------------------------------------------------------------------

    def stage(self, label: str, *, total_stages: int | None = None) -> None:
        if self._status is not None:
            self._app.call_from_thread(self._status.start_stage, label, total_stages)
        if self._bar is not None:
            self._app.call_from_thread(self._bar.set_fraction, 0.0)

    def advance(self, fraction: float, message: str = "") -> None:  # noqa: ARG002
        if self._bar is not None:
            self._app.call_from_thread(self._bar.set_fraction, fraction)

    def log(self, message: str, *, tone: str = "info") -> None:
        if self._log_event is not None:
            self._app.call_from_thread(self._log_event, message, tone)

    # ------------------------------------------------------------------
    # Shell-level helpers (not part of the protocol; safe to ignore)
    # ------------------------------------------------------------------

    def finish(self, summary: str | None = None) -> None:
        """Mark a top-level operation done; reset both sinks to idle."""

        if self._status is not None:
            self._app.call_from_thread(self._status.finish_all, summary)
        if self._bar is not None:
            self._app.call_from_thread(self._bar.hide)


__all__ = [
    "ProgressStrip",
    "StatusStrip",
    "TuiProgressReporter",
]
