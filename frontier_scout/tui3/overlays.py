"""Mission Control (tui3) — modal overlays.

Esc-dismissable modal screens over the dimmed dashboard. This increment ships
Help (keymap + glossary), Notifications (real, via the data adapter), the
command palette (pure navigation), the confirm/typed gates, the result viewer
and the schedule create/edit form (``ScheduleEditorScreen``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from frontier_scout.tui3 import data

KEYS = [
    ("1–8", "jump to a tab"),
    ("j / k  ↑ ↓", "move selection"),
    ("← / →", "change scope"),
    ("s", "run scout now"),
    ("a", "ask (offline)"),
    ("g", "guard"),
    ("r", "refresh tab"),
    ("D", "dossier"),
    ("i", "implement & test"),
    ("e", "evaluate"),
    ("L", "lab"),
    ("p", "command palette"),
    ("n", "notifications"),
    ("X", "clear history"),
    ("R", "reconfigure"),
    ("u", "unicode ↔ ascii"),
    ("c", "color ↔ mono"),
    ("?", "this help & glossary"),
    ("q", "quit"),
]

GLOSSARY = [
    ("ADOPT", "Strong fit, low risk, enough readiness evidence. Safe to bring in."),
    ("TRIAL", "Promising but needs a hands-on try-before-trust run first."),
    ("ASSESS", "Watch and gather evidence; not yet worth integration time."),
    ("HOLD", "Don't adopt now — wrong fit, high risk, or unproven."),
    ("Scout Pack", "A living, curated set of sources for one domain (MCP, models…)."),
    ("Receipt", "A recorded proof of a lab/trial run — what happened, before trust."),
    ("Guard", "The Adoption Firewall: deterministic local policy checks, CI-friendly."),
    ("Lab", "A throwaway hermetic sandbox to probe a tool with a scrubbed env."),
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


class TypedConfirmScreen(_Modal):
    """A destructive gate: the user must type an exact ``token`` to confirm.

    Mirrors ``ConfirmScreen`` but the spend/destructive boundary is the typed
    token. ``on_confirm`` fires ONLY when the submitted text matches ``token``
    exactly (after stripping). A mismatch shows an error and clears the input;
    it never fires the callback. Escape always cancels — even while the Input
    is focused (the ``on_key`` fallback below guarantees it).
    """

    BINDINGS = [
        Binding("escape", "dismiss", "cancel", show=False),
    ]

    def __init__(
        self,
        title: str,
        lines: list[str],
        *,
        token: str,
        on_confirm: Callable[[], None],
    ) -> None:
        super().__init__()
        self._title = title
        self._lines = lines
        self._token = token
        self._on_confirm = on_confirm

    def body(self) -> Iterable[Static]:
        yield self._static(f"[#24d6a8 b]{self._title}[/]")
        for line in self._lines:
            yield self._static(line)
        yield Input(placeholder=f"type '{self._token}' to confirm", id="typed-confirm-input")
        yield Static("", id="typed-confirm-error")
        yield self._static("\n[#6e8aa1]enter confirm · esc cancel[/]")

    def on_mount(self) -> None:
        # Focus the input so the user can type immediately.
        try:
            self.query_one("#typed-confirm-input", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip() == self._token:
            cb = self._on_confirm
            self.app.pop_screen()
            cb()
            return
        # Mismatch: surface an error, clear the field, do NOT fire the callback.
        try:
            self.query_one("#typed-confirm-error", Static).update(
                "[#ff6b6b]does not match — cancelled or retry[/]"
            )
        except Exception:  # noqa: BLE001
            pass
        event.input.value = ""

    def on_key(self, event) -> None:  # noqa: ANN001 — Textual Key event
        """Ensure escape cancels even when the Input has focus."""
        if event.key == "escape":
            event.stop()
            self.action_dismiss()


class ScheduleEditorScreen(_Modal):
    """A create/edit form for a schedule — FOUR text Inputs, Enter to save.

    Generalises ``TypedConfirmScreen``'s single-Input pattern to a small form:
    every field is a plain ``Input`` (no checkboxes) so Enter submits from any
    field with no focus/Enter ambiguity. Creating/editing a schedule is a FREE
    local JSON write — there is NO cost/network gate here. The boundary this
    screen enforces is *validity*: ``on_save`` fires ONLY after every field
    validates, and it receives a normalised dict (``cron_expr`` already passed
    through ``normalise_cron_expr``; ``live`` already a bool). On ANY validation
    failure the error Static is painted red and the modal stays open so the user
    can fix it — the form never raises on bad input, only shows the inline error.
    Escape always cancels (the ``on_key`` fallback guarantees it even while an
    Input is focused).
    """

    BINDINGS = [
        Binding("escape", "dismiss", "cancel", show=False),
    ]

    # field id -> (label, initial-dict key, fallback default)
    _FIELDS = (
        ("f-repo", "repo path", "repo", "."),
        ("f-cron", "cron", "cron_expr", "@daily"),
        ("f-notify", "notify (file/system/disabled)", "notification", "file"),
        ("f-live", "live (yes/no)", "live", "no"),
    )
    _NOTIFY_CHOICES = {"file", "system", "disabled"}
    _LIVE_YES = {"yes", "y", "true", "1", "live", "on"}
    _LIVE_NO = {"no", "n", "false", "0", "dry", "off"}

    def __init__(
        self,
        *,
        title: str,
        initial: dict,
        on_save: Callable[[dict], None],
    ) -> None:
        super().__init__()
        self._title = title
        self._initial = initial or {}
        self._on_save = on_save

    def body(self) -> Iterable[Static]:
        yield self._static(f"[#24d6a8 b]{self._title}[/]")
        for fid, label, key, fallback in self._FIELDS:
            value = str(self._initial.get(key, fallback))
            row = Horizontal(classes="form-row")
            row.compose_add_child(self._static(f"[#6e8aa1]{label}[/]"))
            row.compose_add_child(Input(value=value, id=fid))
            yield row
        yield Static("", id="f-err")
        yield self._static("\n[#6e8aa1]tab move · enter save · esc cancel[/]")

    def on_mount(self) -> None:
        # Focus the repo Input so the user can type immediately (mirrors
        # TypedConfirmScreen's on_mount focus).
        try:
            self.query_one("#f-repo", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def _read(self, fid: str) -> str:
        try:
            return str(self.query_one(f"#{fid}", Input).value)
        except Exception:  # noqa: BLE001
            return ""

    def _error(self, message: str) -> None:
        """Surface an inline error WITHOUT dismissing — never raises."""
        try:
            self.query_one("#f-err", Static).update(f"[#ff6b6b]{message}[/]")
        except Exception:  # noqa: BLE001
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter in ANY field submits the whole form.
        self._submit()

    def _submit(self) -> None:
        repo = self._read("f-repo").strip()
        cron_raw = self._read("f-cron").strip()
        notify = self._read("f-notify").strip().lower()
        live_raw = self._read("f-live").strip().lower()

        # repo: required.
        if not repo:
            self._error("repo path is required")
            return

        # cron: validate via the backend (defensive — accept raw on import error).
        try:
            from frontier_scout import scheduling

            normalised = scheduling.normalise_cron_expr(cron_raw)
            if not scheduling.is_valid_cron_expr(normalised):
                self._error("invalid cron (try @daily, @weekly, or 0 7 * * 1-5)")
                return
        except Exception:  # noqa: BLE001 — backend unavailable: accept raw value
            normalised = cron_raw or "@daily"

        # notify: must be one of the known channels.
        if notify not in self._NOTIFY_CHOICES:
            self._error("notify must be file, system, or disabled")
            return

        # live: parse a permissive yes/no.
        if live_raw in self._LIVE_YES:
            live = True
        elif live_raw in self._LIVE_NO:
            live = False
        else:
            self._error("live must be yes or no")
            return

        # All valid — dismiss FIRST, then fire the callback (mirrors
        # TypedConfirmScreen ordering so the modal is gone before the write).
        cb = self._on_save
        fields = {
            "repo": repo,
            "cron_expr": normalised,
            "notification": notify,
            "live": live,
        }
        self.app.pop_screen()
        cb(fields)

    def on_key(self, event) -> None:  # noqa: ANN001 — Textual Key event
        """Ensure escape cancels even when an Input has focus."""
        if event.key == "escape":
            event.stop()
            self.action_dismiss()


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
    """The notifications list, plus a real "clear all" (c) — a benign local write.

    The list is rendered into ONE id-tagged Static (``#notif-list``) rather than
    a Static-per-row, so "clear all" can repaint it to the empty state IN PLACE
    via ``.update(...)``. That is the codebase's DuplicateIds-safe pattern: we
    never remove + remount child widgets to refresh the list (Textual's
    ``remove_children`` is deferred and would race re-mounted ids). ``c`` is
    bound here so it shadows the global color-toggle ONLY while this modal is
    open; closing it restores the global ``c``.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "close", show=False),
        Binding("q", "dismiss", "close", show=False),
        Binding("c", "clear_all", "clear all", show=False),
    ]

    def _list_markup(self, rows: list[dict] | None = None) -> str:
        """Render the notifications rows (or the empty state) as one markup blob."""
        if rows is None:
            rows = data.notifications_list()
        if not rows:
            return "[#6e8aa1]no notifications[/]"
        lines = []
        for n in rows:
            dot = "[#24d6a8]●[/]" if not n["read"] else "[#6e8aa1]○[/]"
            lines.append(
                f"{dot} [#a9bccd]{n['text']}[/]  [#6e8aa1]{n['repo']} · {n['when']}[/]"
            )
        return "\n".join(lines)

    def body(self) -> Iterable[Static]:
        yield Static("[#24d6a8 b]NOTIFICATIONS[/]")
        yield Static(self._list_markup(), id="notif-list")
        yield Static("\n[#6e8aa1]c clear all · esc close[/]")

    def action_clear_all(self) -> None:
        """Clear every notification (benign local DB write), then repaint empty.

        Refreshes the list to the EMPTY state IN PLACE (updates the single
        ``#notif-list`` Static — never remove + remount rows, which would risk
        DuplicateIds). Surfaces a toast with the count cleared, and best-effort
        refreshes the main header bell/unread count. Never raises.
        """
        n = data.notifications_clear()
        # Repaint the list to the empty state in place (DuplicateIds-safe).
        try:
            self.query_one("#notif-list", Static).update(self._list_markup([]))
        except Exception:  # noqa: BLE001 — refresh must never crash the modal
            pass
        # Toast: confirm the keypress landed (guard the no-op case).
        try:
            if n > 0:
                self.app.notify(f"cleared {n} notification(s)")
            else:
                self.app.notify("no notifications to clear")
        except Exception:  # noqa: BLE001 — notify is best-effort feedback only
            pass
        # Best-effort: refresh the header bell / unread count on the main app.
        try:
            app = self.app
            app.state = app.state.with_(unread=data._unread_count())
            refresh = getattr(app, "_refresh_chrome", None)
            if callable(refresh):
                refresh()
        except Exception:  # noqa: BLE001 — chrome refresh is best-effort only
            pass


# label, action-id (matches an app action_* or a tab id)
PALETTE = [
    ("Go to Scout", "tab:scout"), ("Go to Schedule", "tab:schedule"),
    ("Go to Receipts", "tab:receipts"), ("Go to Guard", "tab:guard"),
    ("Go to Packs", "tab:packs"), ("Go to Deps", "tab:deps"),
    ("Go to Reports", "tab:reports"), ("Go to Settings", "tab:settings"),
    ("Run scout now", "act:scout"), ("Refresh this tab", "act:refresh"),
    ("Build dossier", "act:dossier"), ("Implement & test", "act:implement"),
    ("Evaluate (costs)", "act:evaluate"), ("Lab (sandbox)", "act:lab"),
    ("Clear history", "act:clear"), ("Reconfigure", "act:reconfigure"),
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
