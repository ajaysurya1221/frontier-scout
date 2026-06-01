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
