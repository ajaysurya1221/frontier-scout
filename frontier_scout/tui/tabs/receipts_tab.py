"""Receipts tab — read-only view over the local evidence ledger."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Label, Static

from frontier_scout.store import list_trial_summaries


class ReceiptsTab(VerticalScroll):
    """Master-detail view over stored trial receipts (the evidence ledger)."""

    DEFAULT_CSS = """
    ReceiptsTab .receipts-section {
        margin-bottom: 1;
    }

    ReceiptsTab .receipts-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    ReceiptsTab DataTable {
        background: #0d1622;
        border: round #25405c;
    }

    ReceiptsTab DataTable:focus {
        border: round #24d6a8;
    }

    ReceiptsTab #receipts-detail {
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
        self._rows: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="receipts-section"):
            yield Label("Evidence ledger — local-only", classes="receipts-title")
            yield DataTable(id="receipts-table", cursor_type="row", zebra_stripes=True)
        with Vertical(classes="receipts-section"):
            yield Label("Detail", classes="receipts-title")
            yield Static(
                "[#6e8aa1]Select a receipt above to see decisions, runtime, and the receipt path.[/]",
                id="receipts-detail",
                markup=True,
            )

    def on_mount(self) -> None:
        table = self.query_one("#receipts-table", DataTable)
        table.add_columns("Tool", "Action", "Status", "Decision", "Receipt")
        self._rows = list_trial_summaries(limit=50)
        if not self._rows:
            table.add_row(
                "[dim]no receipts yet[/]",
                "[dim]—[/]",
                "[dim]—[/]",
                "[dim]—[/]",
                "[dim]run a trial from the Scout or Trials tab[/]",
            )
            return
        for row in self._rows:
            table.add_row(
                str(row.get("tool_name") or "—"),
                str(row.get("requested_action") or "—"),
                str(row.get("status") or "—"),
                str(row.get("decision") or "—"),
                str(row.get("primary_url") or "—"),
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._rows:
            return
        try:
            row = self._rows[event.cursor_row]
        except (IndexError, TypeError):
            return
        detail = self.query_one("#receipts-detail", Static)
        lines = [
            f"[#d9f7ff bold]{row.get('tool_name', '—')}[/]",
            f"[#6e8aa1]requested action:[/] {row.get('requested_action', '—')}",
            f"[#6e8aa1]status:           [/] {row.get('status', '—')}",
            f"[#6e8aa1]decision:         [/] {row.get('decision') or '—'}",
            f"[#6e8aa1]primary url:      [/] {row.get('primary_url') or '—'}",
            f"[#6e8aa1]started at:       [/] {row.get('started_at') or '—'}",
            f"[#6e8aa1]finished at:      [/] {row.get('finished_at') or '—'}",
        ]
        detail.update("\n".join(lines))
