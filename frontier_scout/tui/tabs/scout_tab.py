"""Scout tab — the centerpiece. Auto-populated verdict list + per-row actions."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any, ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from frontier_scout.profile import stack_from_profile
from frontier_scout.store import read_setup_state, write_setup_state


_VERDICT_COLORS = {
    "ADOPT": "#24d6a8",
    "TRIAL": "#e3c26f",
    "ASSESS": "#7aa6ff",
    "HOLD": "#ff6b6b",
}


class ScoutTab(VerticalScroll):
    """Default landing tab. Lists the latest AI releases that fit this repo."""

    DEFAULT_CSS = """
    ScoutTab .scout-section {
        margin-bottom: 1;
    }

    ScoutTab .scout-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    ScoutTab .scout-controls {
        height: 3;
    }

    ScoutTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    ScoutTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    ScoutTab DataTable {
        background: #0d1622;
        border: round #25405c;
        height: 14;
    }

    ScoutTab DataTable:focus {
        border: round #24d6a8;
    }

    ScoutTab #scout-detail {
        border: round #25405c;
        padding: 1 2;
        background: #0d1622;
        margin-top: 1;
        height: auto;
    }

    ScoutTab #scout-filter {
        margin-top: 1;
        border: round #25405c;
    }

    ScoutTab #scout-filter:focus {
        border: round #7aa6ff;
    }

    ScoutTab #scout-filter.hidden {
        display: none;
    }
    """

    BINDINGS: ClassVar = [
        Binding("s", "rescout", "Rescout", show=True),
        Binding("l", "live_scout", "Live scout", show=True),
        Binding("slash", "filter", "Filter", show=False),
    ]

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._verdicts: list[dict] = []
        self._filter_value: str = ""
        self._live_armed = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="scout-section"):
            yield Label(
                "Latest AI releases that fit this repo  ·  [s] rescout  [l] live  [/] filter",
                classes="scout-title",
            )
            with Horizontal(classes="scout-controls"):
                yield Button("Trial dry-run", id="scout-trial")
                yield Button("Evaluate", id="scout-evaluate")
                yield Button("Dossier", id="scout-dossier")
                yield Button("Open URL", id="scout-open")
                yield Button("Dismiss", id="scout-dismiss")
            yield DataTable(id="scout-table", cursor_type="row", zebra_stripes=True)
            yield Input(placeholder="filter substring (Esc to clear)", id="scout-filter", classes="hidden")
        with Vertical(classes="scout-section"):
            yield Label("Detail", classes="scout-title")
            yield Static(
                "[#6e8aa1]Scouting…[/]",
                id="scout-detail",
                markup=True,
            )

    def on_mount(self) -> None:
        table = self.query_one("#scout-table", DataTable)
        table.add_columns("Verdict", "Tool", "Fit", "Risk", "Category")
        self._scout_worker(dry_run=True)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _scout_worker(self, *, dry_run: bool) -> None:
        from frontier_scout.scout import run_scan

        repo = Path(self.app_ref.diagnostics.repo)
        payload = run_scan(repo=repo, dry_run=dry_run, persist=not dry_run)
        verdicts = list(payload.get("verdicts") or [])
        self.app_ref.call_from_thread(self._apply_verdicts, verdicts, dry_run)

    def _apply_verdicts(self, verdicts: list[dict], dry_run: bool) -> None:
        dismissed = set(read_setup_state().get("dismissed_tools") or [])
        filtered = [v for v in verdicts if v.get("tool_name") not in dismissed]
        if self._filter_value:
            needle = self._filter_value.lower()
            filtered = [
                v
                for v in filtered
                if needle in str(v.get("tool_name", "")).lower()
                or needle in str(v.get("category", "")).lower()
            ]
        self._verdicts = filtered
        table = self.query_one("#scout-table", DataTable)
        table.clear()
        if not filtered:
            table.add_row("[dim]—[/]", "[dim]no verdicts[/]", "[dim]—[/]", "[dim]—[/]", "[dim]—[/]")
            self.app_ref.log_event(
                f"Scout complete · 0 verdicts ({'live' if not dry_run else 'dry-run'})",
                tone="muted",
            )
            return
        for v in filtered:
            verdict = str(v.get("verdict", "—")).upper()
            color = _VERDICT_COLORS.get(verdict, "#6e8aa1")
            table.add_row(
                f"[{color} bold]{verdict}[/]",
                str(v.get("tool_name", "—")),
                str(v.get("fit", "—")),
                str(v.get("risk", "—")),
                str(v.get("category", "—")),
            )
        kind = "live" if not dry_run else "dry-run"
        self.app_ref.log_event(
            f"Scout complete · {len(filtered)} verdict(s) · {kind}", tone="ok"
        )

    # ------------------------------------------------------------------
    # Row detail
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._verdicts:
            return
        try:
            v = self._verdicts[event.cursor_row]
        except (IndexError, TypeError):
            return
        verdict = str(v.get("verdict", "—")).upper()
        color = _VERDICT_COLORS.get(verdict, "#d9f7ff")
        lines = [
            f"[{color} bold]{verdict}[/]  [#d9f7ff]{v.get('tool_name', '—')}[/]",
            f"[#6e8aa1]category:   [/] {v.get('category', '—')}",
            f"[#6e8aa1]fit:        [/] {v.get('fit', '—')}",
            f"[#6e8aa1]risk:       [/] {v.get('risk', '—')}",
            f"[#6e8aa1]source:     [/] {v.get('source_url', '—')}",
            f"[#6e8aa1]what:       [/] {v.get('what', '—')}",
            f"[#6e8aa1]why:        [/] {v.get('why_it_matters', '—')}",
            f"[#6e8aa1]next:       [/] {v.get('next_safe_step', '—')}",
        ]
        self.query_one("#scout-detail", Static).update("\n".join(lines))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _highlighted_verdict(self) -> dict[str, Any] | None:
        if not self._verdicts:
            return None
        table = self.query_one("#scout-table", DataTable)
        idx = table.cursor_row
        try:
            return self._verdicts[idx]
        except (IndexError, TypeError):
            return None

    @on(Button.Pressed, "#scout-evaluate")
    def _on_evaluate(self) -> None:
        v = self._highlighted_verdict()
        if not v:
            self.app_ref.log_event("No verdict highlighted.", tone="warn")
            return
        url = v.get("source_url") or ""
        if not url:
            self.app_ref.log_event("Selected verdict has no source URL.", tone="warn")
            return
        self._eval_worker(url)

    @work(thread=True, exclusive=True)
    def _eval_worker(self, url: str) -> None:
        from frontier_scout.evaluate import evaluate_url

        stack = stack_from_profile(self.app_ref.diagnostics.profile)
        evaluation = evaluate_url(url, stack)
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Evaluate · {evaluation.tool_name} fit={evaluation.fit} risk={evaluation.risk}",
            "ok",
        )

    @on(Button.Pressed, "#scout-trial")
    def _on_trial(self) -> None:
        v = self._highlighted_verdict()
        if not v:
            self.app_ref.log_event("No verdict highlighted.", tone="warn")
            return
        self._trial_worker(v.get("tool_name", ""), v.get("source_url"))

    @work(thread=True, exclusive=True)
    def _trial_worker(self, tool: str, url: str | None) -> None:
        from frontier_scout.trials import run_trial

        stack = stack_from_profile(self.app_ref.diagnostics.profile)
        result = run_trial(tool, url=url, dry_run=True, stack=stack)
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Trial dry-run receipt for {result.get('tool_name')}: {result.get('receipt_path')}",
            "ok",
        )

    @on(Button.Pressed, "#scout-dossier")
    def _on_dossier(self) -> None:
        v = self._highlighted_verdict()
        if not v:
            self.app_ref.log_event("No verdict highlighted.", tone="warn")
            return
        self._dossier_worker(v.get("tool_name", ""))

    @work(thread=True, exclusive=True)
    def _dossier_worker(self, tool: str) -> None:
        from frontier_scout.dossier import build_dossier

        repo = Path(self.app_ref.diagnostics.repo)
        payload = build_dossier(tool, repo=repo)
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Dossier · {payload.get('tool_name')} → {payload.get('receipt_path')}",
            "ok",
        )

    @on(Button.Pressed, "#scout-open")
    def _on_open(self) -> None:
        v = self._highlighted_verdict()
        if not v:
            return
        url = v.get("source_url") or ""
        if not url:
            return
        webbrowser.open(url)
        self.app_ref.log_event(f"Opened {url}", tone="info")

    @on(Button.Pressed, "#scout-dismiss")
    def _on_dismiss(self) -> None:
        v = self._highlighted_verdict()
        if not v:
            return
        tool = v.get("tool_name") or ""
        if not tool:
            return
        state = read_setup_state()
        dismissed = list(state.get("dismissed_tools") or [])
        if tool not in dismissed:
            dismissed.append(tool)
            state["dismissed_tools"] = dismissed
            write_setup_state(state)
        # Re-apply current verdict set with the new dismiss list.
        self._verdicts = [v for v in self._verdicts if v.get("tool_name") != tool]
        table = self.query_one("#scout-table", DataTable)
        table.remove_row(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key)
        self.app_ref.log_event(f"Dismissed {tool}.", tone="warn")

    # ------------------------------------------------------------------
    # Bindings (rescout, live-scout, filter)
    # ------------------------------------------------------------------

    def action_rescout(self) -> None:
        self.app_ref.log_event("Rescouting (dry-run)…", tone="info")
        self._scout_worker(dry_run=True)

    def action_live_scout(self) -> None:
        if not self._has_api_key():
            self.app_ref.log_event(
                "Live scout requires ANTHROPIC_API_KEY or OPENAI_API_KEY. Skipped.",
                tone="warn",
            )
            return
        if not self._live_armed:
            self._live_armed = True
            self.app_ref.log_event(
                "Press [l] again to confirm a live scout (spends API credits).",
                tone="warn",
            )
            return
        self._live_armed = False
        self.app_ref.log_event("Live scout running…", tone="warn")
        self._scout_worker(dry_run=False)

    def action_filter(self) -> None:
        field = self.query_one("#scout-filter", Input)
        field.remove_class("hidden")
        field.focus()

    @on(Input.Submitted, "#scout-filter")
    def _filter_submit(self, event: Input.Submitted) -> None:
        self._filter_value = event.value.strip()
        self._apply_verdicts(self._raw_payload_cache(), dry_run=True)

    def _raw_payload_cache(self) -> list[dict]:
        """Return the current verdicts including filtered-out ones.

        We re-run the scout because we don't keep an unfiltered cache;
        a small price for filter freshness.
        """
        from frontier_scout.scout import run_scan

        repo = Path(self.app_ref.diagnostics.repo)
        return list(run_scan(repo=repo, dry_run=True, persist=False).get("verdicts") or [])

    def _has_api_key(self) -> bool:
        providers = self.app_ref.diagnostics.providers
        for p in providers:
            if p.name in ("Anthropic API", "OpenAI API") and p.status == "present":
                return True
        return False
