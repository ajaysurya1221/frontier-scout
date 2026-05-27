"""Guard tab — run local policy checks and view findings."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static, Switch

from frontier_scout.guard import format_findings, run_guard


class GuardTab(VerticalScroll):
    """Run guard against the current repo and render findings."""

    DEFAULT_CSS = """
    GuardTab .guard-section {
        margin-bottom: 1;
    }

    GuardTab .guard-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    GuardTab .guard-controls {
        height: 3;
    }

    GuardTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    GuardTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    GuardTab DataTable {
        background: #0d1622;
        border: round #25405c;
        height: 14;
    }

    GuardTab DataTable:focus {
        border: round #24d6a8;
    }

    GuardTab #guard-summary {
        margin-top: 1;
        color: #d9f7ff;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._strict = False
        self._findings: list = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="guard-section"):
            yield Label("Guard — local policy checks", classes="guard-title")
            with Horizontal(classes="guard-controls"):
                yield Button("Run guard", id="guard-run")
                yield Label("strict:", id="guard-strict-label")
                yield Switch(value=False, id="guard-strict")
        with Vertical(classes="guard-section"):
            yield Static("[#6e8aa1]No guard run yet.[/]", id="guard-summary", markup=True)
            yield DataTable(id="guard-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#guard-table", DataTable)
        table.add_columns("Severity", "Tool", "Message")

    @on(Switch.Changed, "#guard-strict")
    def _toggle_strict(self, event: Switch.Changed) -> None:
        self._strict = event.value

    @on(Button.Pressed, "#guard-run")
    def _run(self) -> None:
        self.app_ref.log_event(
            f"Running guard (strict={self._strict})…", tone="info"
        )
        self._run_worker()

    @work(thread=True, exclusive=True)
    def _run_worker(self) -> None:
        repo = Path(self.app_ref.diagnostics.repo)
        findings = run_guard(repo, strict=self._strict)
        self.app_ref.call_from_thread(self._apply_findings, findings)

    def _apply_findings(self, findings: list) -> None:
        self._findings = findings
        table = self.query_one("#guard-table", DataTable)
        table.clear()
        summary = self.query_one("#guard-summary", Static)
        if not findings:
            summary.update("[#24d6a8 bold]Clean.[/] [#6e8aa1]No guard findings.[/]")
            self.app_ref.log_event("Guard: no findings.", tone="ok")
            return
        high = sum(1 for f in findings if getattr(f, "severity", "") == "high")
        medium = sum(1 for f in findings if getattr(f, "severity", "") == "medium")
        low = sum(1 for f in findings if getattr(f, "severity", "") == "low")
        would_fail = high > 0 or (self._strict and medium > 0)
        verdict = (
            "[#ff6b6b bold]would fail CI[/]"
            if would_fail
            else "[#24d6a8 bold]would pass CI[/]"
        )
        summary.update(
            f"{len(findings)} finding(s) · {high} high · {medium} medium · {low} low — {verdict}"
        )
        for f in findings:
            sev = getattr(f, "severity", "—")
            tool = getattr(f, "tool_name", "—")
            msg = getattr(f, "message", "—")
            color = {"high": "#ff6b6b", "medium": "#e3c26f"}.get(sev, "#6e8aa1")
            table.add_row(f"[{color}]{sev}[/]", str(tool), str(msg))
        self.app_ref.log_event(
            f"Guard finished: {len(findings)} finding(s).", tone="warn" if would_fail else "ok"
        )
