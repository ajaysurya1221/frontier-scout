"""Mission Control (tui3) — modal overlays.

Esc-dismissable modal screens over the dimmed dashboard. This increment ships
Help (keymap + glossary), Notifications (real, via the data adapter) and the
command palette (pure navigation); the dossier, diff/result and schedule editor
land in a later increment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from frontier_scout.tui3 import data

KEYS = [
    ("1–8", "jump to a tab"),
    ("j / k  ↑ ↓", "move selection"),
    ("s", "run scout now"),
    ("g", "guard"),
    ("D", "dossier"),
    ("i", "implement & test"),
    ("n", "notifications"),
    ("u", "unicode ↔ ascii"),
    ("c", "color ↔ mono"),
    ("?", "this help"),
    ("q", "quit"),
]

GLOSSARY = [
    ("ADOPT", "Strong fit, low risk, enough evidence. Safe to bring in."),
    ("TRIAL", "Promising but needs a hands-on try-before-trust run first."),
    ("ASSESS", "Watch and gather evidence; not yet worth integration time."),
    ("HOLD", "Don't adopt now — wrong fit, high risk, or unproven."),
    ("Pack", "A living, curated set of sources for one domain (MCP, models…)."),
    ("Receipt", "A recorded proof of a lab/trial run — what happened, before trust."),
    ("Guard", "The Adoption Firewall: deterministic local policy checks, CI-friendly."),
]


class _Modal(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "close", show=False),
        Binding("q", "dismiss", "close", show=False),
    ]

    def body(self) -> Iterable[Static]:  # pragma: no cover - overridden
        return ()

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="panel"):
            yield from self.body()

    def _static(self, markup: str) -> Static:
        """A Static painted for the app's color mode, if the app exposes _paint."""
        paint = getattr(self.app, "_paint", None)
        return Static(paint(markup) if callable(paint) else markup)

    def action_dismiss(self) -> None:
        self.app.pop_screen()


class HelpScreen(_Modal):
    def body(self) -> Iterable[Static]:
        yield Static("[#24d6a8 b]KEYMAP[/]")
        for k, label in KEYS:
            yield Static(f"[#24d6a8 b]{k}[/]   [#6e8aa1]{label}[/]")
        yield Static("\n[#24d6a8 b]GLOSSARY[/]")
        for term, desc in GLOSSARY:
            yield Static(f"[#d9f7ff]{term}[/]  [#6e8aa1]{desc}[/]")
        yield Static("\n[#6e8aa1]esc to close[/]")


class ConfirmScreen(_Modal):
    """A confirm/cost gate: explain, then require an explicit keypress to act.

    The gate is the spend boundary — ``on_confirm`` is only invoked when the
    user presses the confirm key. Escape/q cancel without calling it.

    Bindings are collected by Textual at class-definition time, so the confirm
    key is bound at the class level (``y``, the default). A non-default
    ``confirm_key`` still works via the ``on_key`` fallback below; the footer
    always shows the configured key.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "cancel", show=False),
        Binding("q", "dismiss", "cancel", show=False),
        Binding("y", "confirm", "confirm", show=False),
    ]

    def __init__(
        self,
        title: str,
        lines: list[str],
        on_confirm: Callable[[], None],
        *,
        confirm_key: str = "y",
        confirm_label: str = "confirm",
    ) -> None:
        super().__init__()
        self._title = title
        self._lines = lines
        self._on_confirm = on_confirm
        self._confirm_key = confirm_key
        self._confirm_label = confirm_label

    def body(self) -> Iterable[Static]:
        yield self._static(f"[#24d6a8 b]{self._title}[/]")
        for line in self._lines:
            yield self._static(line)
        yield self._static(
            f"\n[#24d6a8 b]{self._confirm_key}[/] {self._confirm_label}"
            f"   [#6e8aa1]esc cancel[/]"
        )

    def on_key(self, event) -> None:  # noqa: ANN001 — Textual Key event
        """Honour a non-default confirm key (the class binding covers ``y``)."""
        if self._confirm_key != "y" and event.key == self._confirm_key:
            event.stop()
            self.action_confirm()

    def action_confirm(self) -> None:
        # Pop first so the gate is gone before the (slow) worker is kicked.
        self.app.pop_screen()
        self._on_confirm()


class ResultScreen(_Modal):
    """A scrollable viewer for an action result (dossier / implement)."""

    def __init__(self, title: str, lines: list[str]) -> None:
        super().__init__()
        self._title = title
        self._lines = lines

    def body(self) -> Iterable[Static]:
        yield self._static(f"[#24d6a8 b]{self._title}[/]")
        for line in self._lines:
            yield self._static(line)
        yield self._static("\n[#6e8aa1]esc to close[/]")


class NotificationsScreen(_Modal):
    def body(self) -> Iterable[Static]:
        yield Static("[#24d6a8 b]NOTIFICATIONS[/]")
        rows = data.notifications_list()
        if not rows:
            yield Static("\n[#6e8aa1]no notifications[/]")
        for n in rows:
            dot = "[#24d6a8]●[/]" if not n["read"] else "[#6e8aa1]○[/]"
            yield Static(f"{dot} [#a9bccd]{n['text']}[/]  [#6e8aa1]{n['repo']} · {n['when']}[/]")
        yield Static("\n[#6e8aa1]esc to close[/]")


# label, action-id (matches an app action_* or a tab id)
PALETTE = [
    ("Go to Scout", "tab:scout"), ("Go to Schedule", "tab:schedule"),
    ("Go to Receipts", "tab:receipts"), ("Go to Guard", "tab:guard"),
    ("Go to Packs", "tab:packs"), ("Go to Deps", "tab:deps"),
    ("Go to Reports", "tab:reports"), ("Go to Settings", "tab:settings"),
    ("Run scout now", "act:scout"), ("Refresh this tab", "act:refresh"),
    ("Build dossier", "act:dossier"), ("Implement & test", "act:implement"),
    ("Toggle unicode/ascii", "act:unicode"), ("Toggle color/mono", "act:color"),
    ("Help & glossary", "act:help"), ("Notifications", "act:notifications"),
]


class CommandPalette(_Modal):
    """Fuzzy-free command palette: pick a destination or action by number/enter."""

    BINDINGS = [
        Binding("escape", "dismiss", "close", show=False),
        *[Binding(str(d), f"pick({d})", show=False) for d in range(1, 10)],
    ]

    def body(self) -> Iterable[Static]:
        yield Static("[#24d6a8 b]COMMAND PALETTE[/]  [#6e8aa1](esc to close)[/]")
        for i, (label, _aid) in enumerate(PALETTE, start=1):
            key = f"[#24d6a8 b]{i:>2}[/]" if i < 10 else "[#6e8aa1]  [/]"
            yield Static(f"{key} [#a9bccd]{label}[/]")

    def action_pick(self, n: int) -> None:
        if 1 <= n <= len(PALETTE):
            _label, aid = PALETTE[n - 1]
            self.app.pop_screen()
            self.app.run_palette_action(aid)

    def _bindings(self):  # not used directly; see app-level palette dispatch
        return PALETTE
