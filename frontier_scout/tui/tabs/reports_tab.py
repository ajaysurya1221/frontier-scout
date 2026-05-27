"""Reports tab — generate and open static HTML radar reports."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static

from frontier_scout.report import render_html, write_demo
from frontier_scout.store import latest_scan, read_setup_state, write_setup_state


class ReportsTab(VerticalScroll):
    """Buttons that wrap the existing report renderers."""

    DEFAULT_CSS = """
    ReportsTab .reports-section {
        border: round #25405c;
        padding: 1 2;
        margin-bottom: 1;
        background: #0d1622;
    }

    ReportsTab .reports-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    ReportsTab Button {
        margin-right: 1;
        margin-top: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    ReportsTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        with Vertical(classes="reports-section"):
            yield Label("Reports", classes="reports-title")
            yield Static(
                "Render static HTML / Markdown radar reports. Files land under the chosen "
                "output directory; nothing is uploaded.",
                id="reports-help",
            )
            with Horizontal():
                yield Button("Generate offline demo", id="reports-demo")
                yield Button("Render latest scan", id="reports-latest")
        with Vertical(classes="reports-section"):
            yield Label("Recent reports", classes="reports-title")
            yield Static(self._recent_text(), id="reports-recent", markup=True)
            with Horizontal():
                yield Button("Open most recent", id="reports-open")

    @on(Button.Pressed, "#reports-demo")
    def _generate_demo(self) -> None:
        paths = write_demo(Path("demo"))
        path = Path(paths["html"]).resolve()
        self._remember(path)
        self.app_ref.log_event(f"Demo report written: {path}", tone="ok")

    @on(Button.Pressed, "#reports-latest")
    def _render_latest(self) -> None:
        payload = latest_scan()
        if payload is None:
            self.app_ref.log_event(
                "No stored scan found. Run a scout from the Scout tab first.", tone="warn"
            )
            return
        verdicts = list(payload.get("verdicts") or [])
        date = str(payload.get("date") or "latest")
        output = Path("demo") / "briefing.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_html(verdicts, date=date, funnel=payload))
        resolved = output.resolve()
        self._remember(resolved)
        self.app_ref.log_event(f"Latest scan rendered: {resolved}", tone="ok")

    @on(Button.Pressed, "#reports-open")
    def _open_latest(self) -> None:
        recent = read_setup_state().get("recent_reports") or []
        if not recent:
            self.app_ref.log_event("No recent reports yet — generate one first.", tone="warn")
            return
        path = Path(recent[0])
        webbrowser.open(f"file://{path}")
        self.app_ref.log_event(f"Opened {path}", tone="info")

    def _remember(self, path: Path) -> None:
        state = read_setup_state()
        recent = state.get("recent_reports") or []
        recent = [str(path)] + [p for p in recent if p != str(path)]
        state["recent_reports"] = recent[:5]
        write_setup_state(state)
        self.query_one("#reports-recent", Static).update(self._recent_text())

    def _recent_text(self) -> str:
        recent = read_setup_state().get("recent_reports") or []
        if not recent:
            return "[#6e8aa1]No recent reports yet.[/]"
        return "\n".join(f"[#7aa6ff]{p}[/]" for p in recent)
