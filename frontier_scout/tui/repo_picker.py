"""Repo picker modal — shown when ``frontier-scout`` opens outside a repo."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from frontier_scout.store import read_setup_state

REPO_MARKERS = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    ".git",
)

#: Sentinel returned from the picker when the user asks for a
#: universal scout (no repo). v1.2.1 — Stream J. ``runner.py`` reads
#: this and flips ``SetupApp.universal_mode = True``.
UNIVERSAL_SCOUT_SENTINEL = "<UNIVERSAL>"


def looks_like_repo(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_dir():
            return False
    except OSError:
        return False
    for marker in REPO_MARKERS:
        if (path / marker).exists():
            return True
    return False


class RepoPickerScreen(ModalScreen[str | None]):
    """Modal that returns the resolved repo path the user chose, or None."""

    DEFAULT_CSS = """
    RepoPickerScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    RepoPickerScreen #picker-frame {
        width: 80;
        height: auto;
        padding: 1 3;
        border: round #24d6a8;
        background: #0d1622;
    }

    RepoPickerScreen #picker-title {
        text-style: bold;
        color: #d9f7ff;
    }

    RepoPickerScreen #picker-body {
        color: #6e8aa1;
        margin-top: 1;
    }

    RepoPickerScreen Input {
        margin-top: 1;
        border: round #25405c;
    }

    RepoPickerScreen Input:focus {
        border: round #7aa6ff;
    }

    RepoPickerScreen .recent-list {
        margin-top: 1;
    }

    RepoPickerScreen Button {
        margin-right: 1;
        margin-top: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    RepoPickerScreen Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }
    """

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        recent = list(read_setup_state().get("recent_repos") or [])
        with Vertical(id="picker-frame"):
            yield Static("Pick a repo to scout", id="picker-title")
            yield Static(
                "[#6e8aa1]Looks like you're not inside a repo. Type a path below, "
                "or pick one of the shortcuts.[/]",
                id="picker-body",
                markup=True,
            )
            yield Input(placeholder="absolute path · `~` is expanded", id="picker-input")
            yield Static("Shortcuts:", classes="recent-list")
            with Horizontal():
                yield Button(f"$PWD ({os.getcwd()})", id="pick-pwd")
                yield Button(f"$HOME ({Path.home()})", id="pick-home")
            if recent:
                yield Static("Recent repos:", classes="recent-list")
                for i, repo in enumerate(recent[:5]):
                    yield Button(repo, id=f"pick-recent-{i}")
            # Stream J — explicit escape hatches.
            yield Static("Or:", classes="recent-list")
            with Horizontal():
                yield Button(
                    "🌐 Universal scout (no repo)", id="pick-universal"
                )
                yield Button("Quit", id="picker-quit")

        self._recent = recent

    def on_mount(self) -> None:
        self.query_one("#picker-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._try_path(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid in ("picker-cancel", "picker-quit"):
            self.dismiss(None)
        elif bid == "pick-universal":
            self.dismiss(UNIVERSAL_SCOUT_SENTINEL)
        elif bid == "pick-pwd":
            self._try_path(os.getcwd())
        elif bid == "pick-home":
            self._try_path(str(Path.home()))
        elif bid.startswith("pick-recent-"):
            idx = int(bid.removeprefix("pick-recent-"))
            if 0 <= idx < len(self._recent):
                self._try_path(self._recent[idx])

    def _try_path(self, raw: str) -> None:
        if not raw:
            return
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved.exists() and resolved.is_dir():
            self.dismiss(str(resolved))

    def action_cancel(self) -> None:
        self.dismiss(None)
