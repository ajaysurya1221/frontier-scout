"""Click primitives for tui3.

``ClickStatic`` is the single mouse target the whole UI routes through: a painted
``Static`` that, on click, invokes one zero-arg callback. The callback dispatches
to an existing ``action_*``/worker method — never duplicate action logic here
(handoff §5: "one action, two triggers").

``LineClickStatic`` is for multi-line composite Statics (tab rail/strip, verdict
list): it maps the clicked row (``event.y``) to a callback via a line→callback
map, with an optional double-click map (e.g. verdict row → dossier).

Both are plain ``Static`` subclasses, so their content is still painted through
``app._paint`` / ``glyphs`` by the caller — the color/mono and unicode/ascii
fallbacks are unaffected (handoff §6 Bug #6).
"""

from __future__ import annotations

from collections.abc import Callable

from textual import events
from textual.widgets import Static

from frontier_scout.tui3.kit import spinner_frames


# Imported lazily to avoid a circular import (scout_view imports from widgets).
# _scan_progress_line0 is a module-level helper that extracts line 0 from
# scan_progress_lines; widgets.py calls it only at runtime (inside _repaint),
# never at import time.
def _scan_progress_line0(
    repo: str, stage: int, head: int,
    *, label: str = "scanning", frame_idx: int, motion: bool, unicode: bool, width: int
) -> str:
    from frontier_scout.tui3.scout_view import scan_progress_lines  # noqa: PLC0415
    return scan_progress_lines(
        repo, stage, head,
        label=label, frame_idx=frame_idx, motion=motion, unicode=unicode, width=width,
    )[0]


OnClick = Callable[[], None]


class ClickStatic(Static):
    """A painted Static that invokes ``on_click_cb`` when clicked, and
    ``on_dblclick_cb`` on a double-click when one is given."""

    def __init__(
        self,
        renderable: str,
        on_click_cb: OnClick,
        on_dblclick_cb: OnClick | None = None,
        **kw,
    ) -> None:
        super().__init__(renderable, **kw)
        self._on_click_cb = on_click_cb
        self._on_dblclick_cb = on_dblclick_cb

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if self._on_dblclick_cb is not None and getattr(event, "chain", 1) >= 2:
            self._on_dblclick_cb()
        else:
            self._on_click_cb()


class LineClickStatic(Static):
    """A multi-line Static that maps the clicked line index to a callback.

    ``line_map`` is ``{line_index: callback}``. ``dbl_map`` (optional) maps a
    line to a double-click callback. A click on an unmapped line is ignored.
    """

    def __init__(
        self,
        renderable: str,
        line_map: dict[int, OnClick],
        dbl_map: dict[int, OnClick] | None = None,
        **kw,
    ) -> None:
        super().__init__(renderable, **kw)
        self._line_map = line_map
        self._dbl_map = dbl_map or {}

    def set_line_map(self, line_map: dict[int, OnClick], dbl_map: dict[int, OnClick] | None = None) -> None:
        self._line_map = line_map
        self._dbl_map = dbl_map or {}

    def on_click(self, event: events.Click) -> None:
        cb = self._line_map.get(event.y)
        if cb is None:
            return
        event.stop()
        if getattr(event, "chain", 1) >= 2 and event.y in self._dbl_map:
            self._dbl_map[event.y]()
        else:
            cb()


class ScanSpinner(Static):
    """Frame-cycling spinner + glyph radar-sweep, driven by a Textual timer.

    Replaces the v5 CSS-rotated ◉ (a terminal can't rotate a glyph). Renders the
    active spinner frame plus a sweep — a fixed-width run of ``seg_off`` pips with
    one bright ``seg_on`` cell travelling across it (a dim two-cell tail behind it).
    Self-updates via ``.update()`` (never remove+remount → no DuplicateIds); the
    interval auto-cancels on unmount. When ``app.state.motion`` is False the spinner
    holds frame 0 and the sweep is a static mid-lit bar (no interval).

    ``_repaint`` delegates line 0 to ``scan_progress_lines`` (via the module-level
    ``_scan_progress_line0`` shim) so the golden frame is reproducible by both the
    widget and the pure-function test path, with no duplication.
    """

    def __init__(
        self,
        label: str = "scanning",
        *,
        repo: str = "",
        stage: int = 2,
        width: int = 22,
        **kw,
    ) -> None:
        super().__init__("", **kw)
        self._label = label
        self._repo = repo
        self._stage = stage
        self._w = width
        self._frame = 0
        self._head = 0

    def on_mount(self) -> None:
        self._repaint()
        if getattr(self.app.state, "motion", True):
            self.set_interval(0.09, self._tick_frame)
            self.set_interval(0.07, self._tick_sweep)

    def _tick_frame(self) -> None:
        self._frame = (self._frame + 1) % len(spinner_frames(self.app.state.unicode))
        self._repaint()

    def _tick_sweep(self) -> None:
        self._head = (self._head + 1) % self._w
        self._repaint()

    def _repaint(self) -> None:
        uni = self.app.state.unicode
        motion = getattr(self.app.state, "motion", True)
        head = self._head if motion else self._w // 2
        # Delegate line 0 to scan_progress_lines (the golden pure function) so
        # spinner and static render path share the same format invariant.
        # Use self._label for the line-0 spinner label (cap-scan labels flow here);
        # self._repo (or self._label as fallback) goes in the footer.
        repo = self._repo or self._label
        line0 = _scan_progress_line0(
            repo, self._stage, head,
            label=self._label, frame_idx=self._frame, motion=motion, unicode=uni, width=self._w,
        )
        self.update(self.app._paint(line0))
