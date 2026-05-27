"""Trials tab — list existing trials and start new ones."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from frontier_scout.store import list_trial_summaries


class TrialsTab(VerticalScroll):
    """Stored trials + a [+ New Trial] form."""

    DEFAULT_CSS = """
    TrialsTab .trials-section {
        margin-bottom: 1;
    }

    TrialsTab .trials-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    TrialsTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    TrialsTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    TrialsTab DataTable {
        background: #0d1622;
        border: round #25405c;
        height: 12;
    }

    TrialsTab DataTable:focus {
        border: round #24d6a8;
    }

    TrialsTab #trials-form {
        border: round #25405c;
        padding: 1 2;
        background: #0d1622;
        margin-top: 1;
    }

    TrialsTab #trials-form.hidden {
        display: none;
    }

    TrialsTab Input {
        margin-top: 1;
        border: round #25405c;
    }

    TrialsTab Input:focus {
        border: round #7aa6ff;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._rows: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="trials-section"):
            yield Label("Stored trials", classes="trials-title")
            yield DataTable(id="trials-table", cursor_type="row", zebra_stripes=True)
            with Horizontal():
                yield Button("+ New trial (dry-run)", id="trials-new")
                yield Button("Refresh", id="trials-reload")
        with Vertical(id="trials-form", classes="hidden"):
            yield Label("New trial", classes="trials-title")
            yield Input(placeholder="Tool name or repo (e.g. modelcontextprotocol/servers)", id="trials-tool")
            yield Input(placeholder="Source URL (optional)", id="trials-url")
            with Horizontal():
                yield Button("Run dry-run trial", id="trials-submit")
                yield Button("Cancel", id="trials-cancel")

    def on_mount(self) -> None:
        table = self.query_one("#trials-table", DataTable)
        table.add_columns("Tool", "Action", "Status", "Decision")
        self._reload()

    def _reload(self) -> None:
        table = self.query_one("#trials-table", DataTable)
        table.clear()
        self._rows = list_trial_summaries(limit=50)
        if not self._rows:
            table.add_row("[dim]no trials[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
            return
        for row in self._rows:
            table.add_row(
                str(row.get("tool_name", "—")),
                str(row.get("requested_action") or "—"),
                str(row.get("status") or "—"),
                str(row.get("decision") or "—"),
            )

    @on(Button.Pressed, "#trials-reload")
    def _reload_btn(self) -> None:
        self._reload()
        self.app_ref.log_event(f"Trials refreshed · {len(self._rows)} rows.", tone="muted")

    @on(Button.Pressed, "#trials-new")
    def _show_form(self) -> None:
        self.query_one("#trials-form", Vertical).remove_class("hidden")
        self.query_one("#trials-tool", Input).focus()

    @on(Button.Pressed, "#trials-cancel")
    def _hide_form(self) -> None:
        self.query_one("#trials-form", Vertical).add_class("hidden")

    @on(Button.Pressed, "#trials-submit")
    def _submit(self) -> None:
        tool = self.query_one("#trials-tool", Input).value.strip()
        url = self.query_one("#trials-url", Input).value.strip() or None
        if not tool:
            self.app_ref.log_event("Tool name required.", tone="warn")
            return
        self.app_ref.log_event(f"Running dry-run trial for {tool}…", tone="info")
        self._trial_worker(tool, url)

    @work(thread=True, exclusive=True)
    def _trial_worker(self, tool: str, url: str | None) -> None:
        from frontier_scout.trials import run_trial

        stack = {"languages": self.app_ref.diagnostics.profile.languages}
        result = run_trial(tool, url=url, dry_run=True, stack=stack)
        self.app_ref.call_from_thread(self._post_trial, result)

    def _post_trial(self, result: dict) -> None:
        self.app_ref.log_event(
            f"Trial receipt for {result.get('tool_name')}: {result.get('receipt_path')}",
            tone="ok",
        )
        self.query_one("#trials-form", Vertical).add_class("hidden")
        self._reload()
