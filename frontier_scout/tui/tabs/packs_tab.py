"""Packs tab — manage Living Scout Packs."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static

from frontier_scout.packs import ScoutPack, candidate_rows_for_pack, default_packs
from frontier_scout.store import (
    list_pack_candidates,
    list_packs,
    save_builtin_packs_if_empty,
    save_pack_candidate,
)


class PacksTab(VerticalScroll):
    """List packs, show candidates, refresh (with optional discovery)."""

    DEFAULT_CSS = """
    PacksTab .packs-section {
        margin-bottom: 1;
    }

    PacksTab .packs-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    PacksTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    PacksTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    PacksTab DataTable {
        background: #0d1622;
        border: round #25405c;
        height: 12;
    }

    PacksTab DataTable:focus {
        border: round #24d6a8;
    }

    PacksTab #packs-detail {
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
        self._discover_armed = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="packs-section"):
            yield Label("Living Scout Packs", classes="packs-title")
            yield DataTable(id="packs-table", cursor_type="row", zebra_stripes=True)
            with Horizontal():
                yield Button("Refresh seeds", id="packs-refresh")
                yield Button("Refresh + discover (network)", id="packs-discover")
        with Vertical(classes="packs-section"):
            yield Label("Pack detail / candidates", classes="packs-title")
            yield Static(
                "[#6e8aa1]Highlight a pack above to see its definition and current candidates.[/]",
                id="packs-detail",
                markup=True,
            )

    def on_mount(self) -> None:
        save_builtin_packs_if_empty()
        self._reload_rows()

    def _reload_rows(self) -> None:
        table = self.query_one("#packs-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Slug", "Display name", "Seeds")
        self._rows = list_packs()
        if not self._rows:
            table.add_row("[dim]no packs[/]", "—", "—")
            return
        for row in self._rows:
            definition = row.get("definition") or {}
            seeds = len(definition.get("seed_repos") or [])
            table.add_row(str(row.get("slug", "—")), str(row.get("display_name", "—")), str(seeds))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._rows:
            return
        try:
            row = self._rows[event.cursor_row]
        except (IndexError, TypeError):
            return
        definition = row.get("definition") or {}
        seeds = definition.get("seed_repos") or []
        cand = list_pack_candidates(row.get("slug"))
        cand_lines = "\n".join(
            f"  [#7aa6ff]{c.get('state', '?')}[/] [#d9f7ff]{c.get('tool_name', '?')}[/]"
            for c in cand[:10]
        ) or "  [#6e8aa1]no candidates yet — refresh to populate[/]"
        seed_lines = "\n".join(f"  [#24d6a8]{s}[/]" for s in seeds[:10]) or "  [#6e8aa1]no seeds[/]"
        body = "\n".join(
            [
                f"[#d9f7ff bold]{definition.get('display_name', row.get('slug'))}[/]",
                f"[#6e8aa1]{definition.get('description') or ''}[/]",
                "",
                "[#d9f7ff bold]Seeds[/]",
                seed_lines,
                "",
                "[#d9f7ff bold]Candidates[/]",
                cand_lines,
            ]
        )
        self.query_one("#packs-detail", Static).update(body)

    @on(Button.Pressed, "#packs-refresh")
    def _refresh(self) -> None:
        self._discover_armed = False
        self.app_ref.log_event("Refreshing pack candidates from seeds…", tone="info")
        self._refresh_worker(discover=False)

    @on(Button.Pressed, "#packs-discover")
    def _discover(self) -> None:
        if not self._discover_armed:
            self._discover_armed = True
            self.app_ref.log_event(
                "Press again to confirm a live discovery pass (network).", tone="warn"
            )
            return
        self._discover_armed = False
        self.app_ref.log_event("Running live discovery pass…", tone="warn")
        self._refresh_worker(discover=True)

    @work(thread=True, exclusive=True)
    def _refresh_worker(self, *, discover: bool) -> None:
        count = 0
        for row in list_packs():
            pack = ScoutPack(**(row.get("definition") or {}))
            for candidate in candidate_rows_for_pack(pack, discover=discover):
                save_pack_candidate(candidate)
                count += 1
        # Re-warm registry to surface anything newly seeded.
        default_packs()
        self.app_ref.call_from_thread(self._post_refresh, count, discover)

    def _post_refresh(self, count: int, discover: bool) -> None:
        suffix = " with live discovery" if discover else " from seeds"
        self.app_ref.log_event(f"Pack refresh complete · {count} candidates{suffix}.", tone="ok")
        self._reload_rows()
