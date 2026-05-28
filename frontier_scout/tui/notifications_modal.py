"""Notifications modal — lists unread/recent notifications and lets the user
mark-read or clear all."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from frontier_scout.notifications import clear_all, list_notifications, mark_read


class NotificationsScreen(ModalScreen[None]):
    """Modal listing recent notifications grouped newest-first."""

    DEFAULT_CSS = """
    NotificationsScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    NotificationsScreen #notif-frame {
        width: 100;
        height: 32;
        padding: 1 3;
        border: round #7aa6ff;
        background: #0d1622;
    }

    NotificationsScreen #notif-title {
        text-style: bold;
        color: #d9f7ff;
    }

    NotificationsScreen .notif-card {
        border: round #25405c;
        padding: 1 2;
        margin-bottom: 1;
        background: #08131d;
    }

    NotificationsScreen .notif-unread {
        border: round #24d6a8;
    }

    NotificationsScreen Button {
        margin-right: 1;
        margin-top: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    NotificationsScreen Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }
    """

    BINDINGS: ClassVar = [Binding("escape", "close", "Close", show=False)]

    def compose(self) -> ComposeResult:
        notifications = list_notifications()
        with Vertical(id="notif-frame"):
            unread = len([n for n in notifications if not n.get("read")])
            yield Static(
                f"Notifications · {len(notifications)} total · {unread} unread",
                id="notif-title",
            )
            if not notifications:
                yield Static(
                    "[#6e8aa1]No notifications yet. Schedule a scout from the wizard "
                    "(or Settings → Automation) to get notified when new ADOPT / TRIAL "
                    "verdicts appear.[/]",
                    markup=True,
                )
            else:
                with VerticalScroll():
                    for n in notifications:
                        cls = "notif-card notif-unread" if not n.get("read") else "notif-card"
                        with Vertical(classes=cls):
                            yield Static(
                                f"[#d9f7ff bold]{n.get('repo', '—')}[/]  "
                                f"[#6e8aa1]{n.get('timestamp', '—')}[/]",
                                markup=True,
                            )
                            new = n.get("new_verdicts") or []
                            for v in new[:5]:
                                verdict = str(v.get("verdict", "—")).upper()
                                color = {
                                    "ADOPT": "#24d6a8",
                                    "TRIAL": "#e3c26f",
                                }.get(verdict, "#7aa6ff")
                                yield Static(
                                    f"  [{color}]{verdict}[/] "
                                    f"[#d9f7ff]{v.get('tool_name', '—')}[/]",
                                    markup=True,
                                )
                            if not n.get("read"):
                                yield Button(
                                    "Mark read", id=f"notif-mark-{n.get('_path')}"
                                )
            with Horizontal():
                yield Button("Clear all", id="notif-clear")
                yield Button("Close (Esc)", id="notif-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "notif-close":
            self.dismiss(None)
        elif bid == "notif-clear":
            clear_all()
            self.dismiss(None)
        elif bid.startswith("notif-mark-"):
            path = bid.removeprefix("notif-mark-")
            mark_read(path)
            event.button.disabled = True
            event.button.label = "Read ✓"

    def action_close(self) -> None:
        self.dismiss(None)
