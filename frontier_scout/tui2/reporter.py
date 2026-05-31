"""A ProgressReporter that posts Textual messages from a worker thread.

The backends (``scout.run_scan``, ``implement.run_implement``, …) all accept an
optional ``reporter`` implementing :class:`frontier_scout.progress.ProgressReporter`.
``TuiReporter`` forwards their staged events to the app as :class:`Progress`
messages, using ``app.post_message`` which is safe to call from a worker thread.
"""

from __future__ import annotations

from typing import Any


class TuiReporter:
    """Bridges backend progress events onto the Textual message bus.

    Implements the :class:`frontier_scout.progress.ProgressReporter` protocol
    (``stage`` / ``advance`` / ``log``). Held by the worker, never by a widget.
    """

    def __init__(self, app: Any) -> None:
        self._app = app
        self._last_stage: str | None = None

    def stage(self, label: str, total_stages: int | None = None) -> None:
        from frontier_scout.tui2.messages import Progress

        # Mark the previous stage complete (✓) before announcing the new one.
        if self._last_stage and self._last_stage != label:
            self._app.post_message(Progress(self._last_stage, done=True))
        self._last_stage = label
        self._app.post_message(Progress(label))

    def advance(self, fraction: float, message: str = "") -> None:  # noqa: ARG002
        if message:
            from frontier_scout.tui2.messages import Progress

            self._app.post_message(Progress(message))

    def log(self, message: str, tone: str = "info") -> None:
        from frontier_scout.tui2.messages import Progress

        self._app.post_message(Progress(message, tone=tone))
