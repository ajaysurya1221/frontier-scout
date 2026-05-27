"""Deps tab — dependency intelligence scan + trial creation."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static


class DepsTab(VerticalScroll):
    """Scan for meaningful upgrades, optionally write a trial receipt."""

    DEFAULT_CSS = """
    DepsTab .deps-section {
        margin-bottom: 1;
    }

    DepsTab .deps-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    DepsTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    DepsTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    DepsTab DataTable {
        background: #0d1622;
        border: round #25405c;
        height: 14;
    }

    DepsTab DataTable:focus {
        border: round #24d6a8;
    }

    DepsTab #deps-detail {
        border: round #25405c;
        padding: 1 2;
        background: #0d1622;
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._findings: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="deps-section"):
            yield Label("Dependency intelligence", classes="deps-title")
            with Horizontal():
                yield Button("Run scan", id="deps-run")
                yield Button("Create trial for highlighted", id="deps-trial")
            yield DataTable(id="deps-table", cursor_type="row", zebra_stripes=True)
        with Vertical(classes="deps-section"):
            yield Label("Detail", classes="deps-title")
            yield Static(
                "[#6e8aa1]Run scan to find security / hardening / breaking upgrades.[/]",
                id="deps-detail",
                markup=True,
            )

    def on_mount(self) -> None:
        table = self.query_one("#deps-table", DataTable)
        table.add_columns("Verdict", "Package", "From", "To", "Classification")

    @on(Button.Pressed, "#deps-run")
    def _run(self) -> None:
        self.app_ref.log_event("Scanning dependencies…", tone="info")
        self._run_worker()

    @work(thread=True, exclusive=True)
    def _run_worker(self) -> None:
        from frontier_scout.dependencies import run_dependency_scan

        repo = Path(self.app_ref.diagnostics.repo)
        payload = run_dependency_scan(repo)
        findings = list(payload.get("findings") or [])
        self.app_ref.call_from_thread(self._apply_findings, findings)

    def _apply_findings(self, findings: list[dict]) -> None:
        self._findings = findings
        table = self.query_one("#deps-table", DataTable)
        table.clear()
        if not findings:
            table.add_row("[dim]—[/]", "[dim]no findings[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
            self.app_ref.log_event("Deps scan: 0 findings.", tone="ok")
            return
        for f in findings:
            verdict = str(f.get("verdict", "—")).upper()
            color = {
                "ADOPT": "#24d6a8",
                "TRIAL": "#e3c26f",
                "ASSESS": "#7aa6ff",
                "HOLD": "#ff6b6b",
            }.get(verdict, "#6e8aa1")
            table.add_row(
                f"[{color} bold]{verdict}[/]",
                str(f.get("package_name", "—")),
                str(f.get("from_version", "—")),
                str(f.get("to_version", "—")),
                str(f.get("classification", "—")),
            )
        self.app_ref.log_event(f"Deps scan complete: {len(findings)} finding(s).", tone="ok")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._findings:
            return
        try:
            f = self._findings[event.cursor_row]
        except (IndexError, TypeError):
            return
        lines = [
            f"[#d9f7ff bold]{f.get('package_name', '—')}[/]",
            f"[#6e8aa1]verdict:       [/] {str(f.get('verdict', '—')).upper()}",
            f"[#6e8aa1]from -> to:    [/] {f.get('from_version', '—')} -> {f.get('to_version', '—')}",
            f"[#6e8aa1]classification:[/] {f.get('classification', '—')}",
            f"[#6e8aa1]why:           [/] {f.get('why_it_matters') or '—'}",
            f"[#6e8aa1]severity:      [/] {f.get('severity') or '—'}",
        ]
        self.query_one("#deps-detail", Static).update("\n".join(lines))

    @on(Button.Pressed, "#deps-trial")
    def _trial(self) -> None:
        if not self._findings:
            self.app_ref.log_event("Run scan first.", tone="warn")
            return
        table = self.query_one("#deps-table", DataTable)
        idx = table.cursor_row
        try:
            f = self._findings[idx]
        except (IndexError, TypeError):
            self.app_ref.log_event("No row highlighted.", tone="warn")
            return
        self.app_ref.log_event(
            f"Creating dependency trial for {f.get('package_name')} "
            f"{f.get('from_version')} -> {f.get('to_version')}…",
            tone="info",
        )
        self._trial_worker(f)

    @work(thread=True, exclusive=True)
    def _trial_worker(self, f: dict) -> None:
        from frontier_scout.dep_trial import run_dependency_trial

        repo = Path(self.app_ref.diagnostics.repo)
        result = run_dependency_trial(
            f["package_name"],
            from_version=f.get("from_version", ""),
            to_version=f.get("to_version", ""),
            repo=repo,
            dry_run=True,
        )
        self.app_ref.call_from_thread(self._post_trial, result)

    def _post_trial(self, result: dict) -> None:
        path = result.get("receipt_path", "—")
        self.app_ref.log_event(
            f"Dependency trial receipt: {path} · {result.get('lab_result', {}).get('status')}",
            tone="ok",
        )
