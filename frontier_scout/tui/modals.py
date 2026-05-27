"""Modal screens used by mission control: quit confirmation and help."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_BODY = """\
Navigation
  1 — 9             jump to tab by number
  Tab / Shift-Tab   cycle widgets within active tab
  ↑ ↓               move within tables
  Enter             run focused action / submit field

Scout tab
  s                 rescout (dry-run)
  l                 live scout (requires API key + double-press)
  /                 filter substring

System
  /                 change repo path (when not on Scout filter)
  ?                 toggle this help
  Ctrl-L            clear result log
  q                 quit (confirmation required)
  Esc               close modal / cancel
"""


class QuitConfirmScreen(ModalScreen[bool]):
    """Yes/No quit prompt that returns True to exit, False to stay."""

    DEFAULT_CSS = """
    QuitConfirmScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    QuitConfirmScreen #quit-frame {
        width: 48;
        height: auto;
        padding: 1 3;
        border: round #24d6a8;
        background: #0d1622;
    }

    QuitConfirmScreen #quit-title {
        text-style: bold;
        color: #d9f7ff;
    }

    QuitConfirmScreen #quit-body {
        color: #6e8aa1;
        margin-top: 1;
    }

    QuitConfirmScreen #quit-keys {
        margin-top: 1;
        color: #e3c26f;
    }
    """

    BINDINGS: ClassVar = [
        Binding("y", "confirm(True)", "Quit", show=False),
        Binding("enter", "confirm(True)", "Quit", show=False),
        Binding("n", "confirm(False)", "Stay", show=False),
        Binding("escape", "confirm(False)", "Stay", show=False),
        Binding("q", "confirm(True)", "Quit", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-frame"):
            yield Static("Quit Frontier Scout setup?", id="quit-title")
            yield Static(
                "Your selections and action history will be lost. The repo "
                "profile already saved to ~/.frontier-scout stays put.",
                id="quit-body",
            )
            yield Static("[Y]es / [Enter] — quit · [N]o / [Esc] — stay", id="quit-keys")

    def action_confirm(self, decision: bool) -> None:
        self.dismiss(decision)


class HelpScreen(ModalScreen[None]):
    """Keymap overlay shown when the user presses ?."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    HelpScreen #help-frame {
        width: 60;
        height: auto;
        padding: 1 3;
        border: round #e3c26f;
        background: #0d1622;
    }

    HelpScreen #help-title {
        text-style: bold;
        color: #d9f7ff;
    }

    HelpScreen #help-body {
        margin-top: 1;
        color: #d9f7ff;
    }

    HelpScreen #help-footer {
        margin-top: 1;
        color: #6e8aa1;
    }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "close", "Close", show=False),
        Binding("?", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-frame"):
            yield Static("Frontier Scout — keys", id="help-title")
            yield Static(_HELP_BODY, id="help-body")
            yield Static("press Esc, ?, or Enter to close", id="help-footer")

    def action_close(self) -> None:
        self.dismiss(None)


class RepoPathPromptScreen(ModalScreen[str | None]):
    """Modal Input for typing a new repo path; returns the typed path or None."""

    DEFAULT_CSS = """
    RepoPathPromptScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    RepoPathPromptScreen #repo-frame {
        width: 70;
        height: auto;
        padding: 1 3;
        border: round #7aa6ff;
        background: #0d1622;
    }

    RepoPathPromptScreen #repo-title {
        text-style: bold;
        color: #d9f7ff;
    }

    RepoPathPromptScreen #repo-hint {
        color: #6e8aa1;
        margin-top: 1;
    }

    RepoPathPromptScreen Input {
        margin-top: 1;
        border: round #25405c;
    }

    RepoPathPromptScreen Input:focus {
        border: round #24d6a8;
    }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, current_value: str) -> None:
        super().__init__()
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        from textual.widgets import Input

        with Vertical(id="repo-frame"):
            yield Static("Change repo path", id="repo-title")
            yield Static(
                "Type an absolute path or `.` for the current directory. "
                "Press Enter to refresh diagnostics. Esc cancels.",
                id="repo-hint",
            )
            yield Input(value=self._current_value, id="repo-input")

    def on_mount(self) -> None:
        from textual.widgets import Input

        self.query_one("#repo-input", Input).focus()

    def on_input_submitted(self, event) -> None:
        self.dismiss(str(event.value))

    def action_cancel(self) -> None:
        self.dismiss(None)
