"""Diff modal — compare the current scout against the previous one for a repo."""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class DiffScreen(ModalScreen[None]):
    """Shows New / Changed / Retired verdicts against the previous scan."""

    DEFAULT_CSS = """
    DiffScreen {
        align: center middle;
        background: #0b1117 50%;
    }

    DiffScreen #diff-frame {
        width: 96;
        height: 28;
        padding: 1 3;
        border: round #24d6a8;
        background: #0d1622;
    }

    DiffScreen #diff-title {
        text-style: bold;
        color: #d9f7ff;
    }

    DiffScreen .diff-section-title {
        text-style: bold;
        color: #d9f7ff;
        margin-top: 1;
    }

    DiffScreen Button {
        margin-top: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    DiffScreen Button:focus {
        border: round #24d6a8;
    }
    """

    BINDINGS: ClassVar = [Binding("escape", "close", "Close", show=False)]

    def __init__(
        self,
        *,
        current: list[dict[str, Any]],
        previous: list[dict[str, Any]],
    ) -> None:
        super().__init__()
        self._current = current
        self._previous = previous

    def compose(self) -> ComposeResult:
        prev_by_tool = {v.get("tool_name"): v for v in self._previous if v.get("tool_name")}
        cur_by_tool = {v.get("tool_name"): v for v in self._current if v.get("tool_name")}

        new_tools = [
            v for v in self._current if v.get("tool_name") not in prev_by_tool
        ]
        retired_tools = [
            v for v in self._previous if v.get("tool_name") not in cur_by_tool
        ]
        changed: list[tuple[dict, dict]] = []
        for tool, cur in cur_by_tool.items():
            prev = prev_by_tool.get(tool)
            if prev is None:
                continue
            if any(
                str(cur.get(k, "")).lower() != str(prev.get(k, "")).lower()
                for k in ("verdict", "fit", "risk")
            ):
                changed.append((prev, cur))

        with Vertical(id="diff-frame"):
            yield Static(
                f"Scout diff · current vs previous · "
                f"[#24d6a8]{len(new_tools)} new[/] · "
                f"[#e3c26f]{len(changed)} changed[/] · "
                f"[#6e8aa1]{len(retired_tools)} retired[/]",
                id="diff-title",
                markup=True,
            )
            with VerticalScroll():
                if not (new_tools or changed or retired_tools):
                    yield Static(
                        "[#6e8aa1]No differences. The radar is steady — no new "
                        "ADOPT / TRIAL / ASSESS / HOLD calls and no risk shifts.[/]",
                        markup=True,
                    )
                if new_tools:
                    yield Static("New", classes="diff-section-title")
                    for v in new_tools:
                        verdict = str(v.get("verdict", "—")).upper()
                        yield Static(
                            f"  [#24d6a8]{verdict:<7}[/] "
                            f"[#d9f7ff]{v.get('tool_name', '—')}[/]  "
                            f"[#6e8aa1](fit {v.get('fit', '—')} · risk {v.get('risk', '—')})[/]",
                            markup=True,
                        )
                if changed:
                    yield Static("Changed", classes="diff-section-title")
                    for prev, cur in changed:
                        yield Static(
                            f"  [#e3c26f]{str(prev.get('verdict','')).upper()}→"
                            f"{str(cur.get('verdict','')).upper():<6}[/] "
                            f"[#d9f7ff]{cur.get('tool_name', '—')}[/]  "
                            f"[#6e8aa1](fit {prev.get('fit','—')}→{cur.get('fit','—')} · "
                            f"risk {prev.get('risk','—')}→{cur.get('risk','—')})[/]",
                            markup=True,
                        )
                if retired_tools:
                    yield Static("Retired", classes="diff-section-title")
                    for v in retired_tools:
                        yield Static(
                            f"  [#6e8aa1]{str(v.get('verdict','—')).upper():<7}[/] "
                            f"[#6e8aa1]{v.get('tool_name', '—')}[/]  "
                            "[#6e8aa1](dropped this run)[/]",
                            markup=True,
                        )
            with Horizontal():
                yield Button("Close (Esc)", id="diff-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "diff-close":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
