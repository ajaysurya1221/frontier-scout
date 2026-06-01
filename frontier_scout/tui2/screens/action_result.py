"""ActionResultScreen — "here's what you got" after an action runs.

For Implement & test: summary, what you get, files changed, tests pass/fail,
and the diff (scrollable in the Body). ``Enter`` keeps changes (only when the
run passed), ``Esc`` returns to the card. For lighter actions (explain) it just
shows the prose payload.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from frontier_scout.tui2.screens.base import BriefingScreen

_STATUS_TONE = {"passed": "ok", "failed": "warn", "prepared": "info", "error": "muted"}
# Filled status pill: (foreground, background) per tone, matching the design.
_PILL = {
    "ok": ("#06231b", "#24d6a8"),
    "info": ("#091a36", "#7aa6ff"),
    "warn": ("#2b2208", "#e3c26f"),
    "muted": ("#d9f7ff", "#25405c"),
}


class ActionResultScreen(BriefingScreen):
    BINDINGS = [
        Binding("enter", "keep", "keep", show=False),
        Binding("escape", "back", "back", show=False),
    ]

    def __init__(self, kind: str, payload: Any) -> None:
        super().__init__()
        self._kind = kind
        self._payload = payload
        self._kept = False

    def compass_text(self) -> str:
        if self._kind == "implement" and getattr(self._payload, "status", "") == "passed" and not self._kept:
            return "⏎ keep changes · esc back to card"
        return "esc back"

    def body(self) -> Iterable[Widget]:
        if self._kind == "implement":
            yield from self._implement_body()
        else:
            yield from self._text_body()

    def _text_body(self) -> Iterable[Widget]:
        title, text = self._payload
        yield Static(title, classes="title")
        yield Static(text, classes="prose")

    def _implement_body(self) -> Iterable[Widget]:
        r = self._payload
        tone = _STATUS_TONE.get(r.status, "muted")
        fg, bg = _PILL.get(tone, _PILL["muted"])
        yield Static(f"[{fg} on {bg}] {r.status.upper()} [/]   [dim]{r.tool_name}[/dim]", classes="ribbon")
        if r.summary:
            yield Static(r.summary, classes="prose")
        if r.what_you_get:
            yield Static("WHAT YOU GET", classes="block-h")
            yield Static(r.what_you_get, classes="prose")
        if r.files_changed:
            yield Static("FILES CHANGED", classes="block-h")
            files = "\n".join(f"  [#24d6a8]•[/] {f}" for f in r.files_changed)
            yield Static(files, classes="prose")
        if r.test_command:
            verdict = "[#24d6a8]passed ✓[/]" if r.status == "passed" else f"[#ff6b6b]failed (exit {r.exit_code})[/]"
            yield Static("TESTS", classes="block-h")
            yield Static(f"{r.test_command} → {verdict}", classes="prose")
        if r.error:
            yield Static("ERROR", classes="block-h")
            yield Static(r.error, classes="prose")
        if r.diff:
            yield Static("DIFF", classes="block-h")
            yield Static(r.diff, classes="prose")
        if r.status == "passed":
            yield Static("[dim]⏎ keep these changes in your working tree[/dim]", classes="prose")
        yield Static("[dim]esc — discard the isolated copy and go back[/dim]", classes="prose")

    def action_keep(self) -> None:
        if self._kind != "implement" or self._kept:
            return
        r = self._payload
        if getattr(r, "status", "") != "passed":
            return
        self.app.keep_implement(r)
        self._kept = True
        try:
            self.query_one("#compass", Static).update("kept ✓ · esc back")
        except Exception:  # noqa: BLE001
            pass

    def action_back(self) -> None:
        if self._kind == "implement" and not self._kept:
            self.app.discard_implement(self._payload)
        self.app.pop_screen()
