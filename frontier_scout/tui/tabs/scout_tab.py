"""Scout tab — v1.2.

One unified verdict list (AI tools + dependency upgrades). Auto-focused
DataTable with the cursor on row 0 so action buttons always have a
target. A rich detail panel default-populated to the first row so the
reasoning is visible without keystrokes. A guard banner that appears
inline when policy findings need a sandbox receipt.

No splash, no welcome modal, no URL paste, no demo.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any, ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Static

from frontier_scout.profile import stack_from_profile
from frontier_scout.store import read_setup_state, write_setup_state


_VERDICT_COLORS = {
    "ADOPT": "#24d6a8",
    "TRIAL": "#e3c26f",
    "ASSESS": "#7aa6ff",
    "HOLD": "#ff6b6b",
}

_DEP_VERDICT_COLORS = {
    "TRIAL": "#e3c26f",
    "ASSESS": "#7aa6ff",
    "HOLD": "#ff6b6b",
}


class ScoutTab(VerticalScroll):
    """The product, in one tab."""

    DEFAULT_CSS = """
    ScoutTab .scout-controls {
        height: 3;
        margin-bottom: 1;
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

    ScoutTab Button.scope-active {
        border: round #24d6a8;
        color: #24d6a8;
    }

    ScoutTab #scout-guard-banner {
        border: round #e3c26f;
        background: #1a1408;
        color: #e3c26f;
        padding: 0 1;
        margin-bottom: 1;
    }

    ScoutTab #scout-guard-banner.hidden {
        display: none;
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
        background: #0d1622;
        padding: 1 2;
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS: ClassVar = [
        Binding("s", "rescout", "Rescout", show=True),
        Binding("c", "clear_memory", "Clear memory", show=True),
        Binding("enter", "primary_action", "Try locally", show=True),
    ]

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._rows: list[dict[str, Any]] = []
        self._guard_findings: list = []
        state = read_setup_state()
        self._scope_ai = bool(state.get("scout_scope_ai", True))
        self._scope_deps = bool(state.get("scout_scope_deps", True))

    # ------------------------------------------------------------------
    # Compose / mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(classes="scout-controls"):
            yield Button(self._scope_label("ai"), id="scout-toggle-ai", classes=self._scope_class("ai"))
            yield Button(self._scope_label("deps"), id="scout-toggle-deps", classes=self._scope_class("deps"))
            yield Static("", id="scout-status")
        yield Static("", id="scout-guard-banner", classes="hidden", markup=True)
        yield DataTable(id="scout-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="scout-controls"):
            yield Button("Try locally  (Enter)", id="scout-try")
            yield Button("Open URL", id="scout-open")
            yield Button("Dismiss", id="scout-dismiss")
        yield Static(
            "[#6e8aa1]Scouting your repo…[/]",
            id="scout-detail",
            markup=True,
        )

    def on_mount(self) -> None:
        table = self.query_one("#scout-table", DataTable)
        table.add_columns("Verdict", "Tool / Package", "Fit", "Risk", "Category")
        self._scout_worker()

    # ------------------------------------------------------------------
    # Scope toggles
    # ------------------------------------------------------------------

    def _scope_label(self, kind: str) -> str:
        if kind == "ai":
            return "[×] AI tools" if self._scope_ai else "[ ] AI tools"
        return "[×] Dependencies" if self._scope_deps else "[ ] Dependencies"

    def _scope_class(self, kind: str) -> str:
        active = self._scope_ai if kind == "ai" else self._scope_deps
        return "scope-active" if active else ""

    @on(Button.Pressed, "#scout-toggle-ai")
    def _toggle_ai(self) -> None:
        self._scope_ai = not self._scope_ai
        self._persist_scope()
        self._refresh_scope_buttons()
        self._scout_worker()

    @on(Button.Pressed, "#scout-toggle-deps")
    def _toggle_deps(self) -> None:
        self._scope_deps = not self._scope_deps
        self._persist_scope()
        self._refresh_scope_buttons()
        self._scout_worker()

    def _refresh_scope_buttons(self) -> None:
        ai = self.query_one("#scout-toggle-ai", Button)
        deps = self.query_one("#scout-toggle-deps", Button)
        ai.label = self._scope_label("ai")
        deps.label = self._scope_label("deps")
        if self._scope_ai:
            ai.add_class("scope-active")
        else:
            ai.remove_class("scope-active")
        if self._scope_deps:
            deps.add_class("scope-active")
        else:
            deps.remove_class("scope-active")

    def _persist_scope(self) -> None:
        state = read_setup_state()
        state["scout_scope_ai"] = self._scope_ai
        state["scout_scope_deps"] = self._scope_deps
        write_setup_state(state)

    # ------------------------------------------------------------------
    # Scout worker (AI + Deps + Guard in one go)
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _scout_worker(self) -> None:
        from frontier_scout.scout import run_scan

        repo = Path(self.app_ref.diagnostics.repo)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []

        if self._scope_ai:
            try:
                payload = run_scan(repo=repo, dry_run=True, persist=True)
                for v in payload.get("verdicts") or []:
                    rows.append(self._ai_verdict_to_row(v))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"AI scan failed: {exc}")

        if self._scope_deps:
            try:
                from frontier_scout.dependencies import run_dependency_scan

                payload = run_dependency_scan(repo, persist=False)
                for f in payload.get("findings") or []:
                    row = self._dep_finding_to_row(f)
                    if row is not None:
                        rows.append(row)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Dependency scan failed: {exc}")

        guard_findings: list = []
        try:
            from frontier_scout.guard import run_guard

            guard_findings = run_guard(repo) or []
        except Exception:
            guard_findings = []

        self.app_ref.call_from_thread(self._apply_results, rows, guard_findings, errors)

    def _apply_results(
        self,
        rows: list[dict[str, Any]],
        guard_findings: list,
        errors: list[str],
    ) -> None:
        dismissed = set(read_setup_state().get("dismissed_tools") or [])
        rows = [r for r in rows if r.get("tool_name") not in dismissed]
        self._rows = rows
        self._guard_findings = guard_findings

        table = self.query_one("#scout-table", DataTable)
        table.clear()
        if errors:
            for err in errors:
                self.app_ref.log_event(err, tone="error")
        if not rows:
            self._render_empty()
        else:
            for r in rows:
                color = _VERDICT_COLORS.get(r["verdict"], "#6e8aa1")
                table.add_row(
                    f"[{color} bold]{r['verdict']}[/]",
                    r["tool_name"],
                    r["fit"],
                    r["risk"],
                    r["category"],
                )
            # Auto-focus + auto-cursor — the v1.1 bug we are fixing.
            table.cursor_coordinate = (0, 0)
            table.focus()
            self._render_detail(rows[0])

        self._render_guard_banner(guard_findings)
        status = self.query_one("#scout-status", Static)
        status.update(f"[#6e8aa1]· {len(rows)} finding(s) · press [s] to rescout[/]")
        self.app_ref.log_event(
            f"Scout complete · {len(rows)} finding(s) · {len(guard_findings)} guard alert(s)",
            tone="ok",
        )

    def _render_empty(self) -> None:
        table = self.query_one("#scout-table", DataTable)
        table.add_row(
            "[dim]—[/]",
            "[dim]nothing found yet — toggle a scope above or press [s][/]",
            "[dim]—[/]",
            "[dim]—[/]",
            "[dim]—[/]",
        )
        self.query_one("#scout-detail", Static).update(
            "[#6e8aa1]Nothing to show. Enable a scope (AI tools / Dependencies) "
            "above the table, or press [s] to rescout.[/]"
        )

    def _render_guard_banner(self, findings: list) -> None:
        banner = self.query_one("#scout-guard-banner", Static)
        risky = [
            f
            for f in findings
            if getattr(f, "severity", "") in ("high", "medium")
        ]
        if not risky:
            banner.add_class("hidden")
            banner.update("")
            return
        banner.remove_class("hidden")
        names = []
        for f in risky[:3]:
            tool = getattr(f, "tool_name", None) or "unknown"
            msg = getattr(f, "message", "needs a guard receipt")
            names.append(f"  ▏ [#d9f7ff]{tool}[/] — {msg}")
        body = (
            f"[bold]⚠  {len(risky)} tool(s) need a guard receipt before adoption.[/]\n"
            + "\n".join(names)
            + "\n  [#6e8aa1]Highlight the tool in the table and press Enter to write a dry-run trial receipt.[/]"
        )
        banner.update(body)

    # ------------------------------------------------------------------
    # Row → dict shapes
    # ------------------------------------------------------------------

    def _ai_verdict_to_row(self, v: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "ai",
            "verdict": str(v.get("verdict", "—")).upper(),
            "tool_name": v.get("tool_name", "—"),
            "fit": v.get("fit", "—"),
            "risk": v.get("risk", "—"),
            "category": v.get("category", "—"),
            "source_url": v.get("source_url"),
            "raw": v,
        }

    def _dep_finding_to_row(self, f: dict[str, Any]) -> dict[str, Any] | None:
        verdict = str(f.get("verdict", "")).upper()
        if not verdict:
            return None
        return {
            "kind": "dep",
            "verdict": verdict,
            "tool_name": (
                f"{f.get('package_name', '?')} "
                f"{f.get('from_version', '?')} → {f.get('to_version', '?')}"
            ),
            "fit": f.get("repo_fit", "—"),
            "risk": self._classification_to_risk(f.get("classification", "")),
            "category": f"dependency:{f.get('classification', 'unknown')}",
            "source_url": None,
            "raw": f,
        }

    def _classification_to_risk(self, classification: str) -> str:
        return {
            "security": "high",
            "breaking": "high",
            "hardening": "medium",
            "feature": "low",
            "noise": "low",
        }.get(classification, "—")

    # ------------------------------------------------------------------
    # Detail panel — the reasoning surface
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._rows:
            return
        try:
            row = self._rows[event.cursor_row]
        except (IndexError, TypeError):
            return
        self._render_detail(row)

    def _render_detail(self, row: dict[str, Any]) -> None:
        if row["kind"] == "ai":
            text = self._ai_detail(row["raw"], row["verdict"])
        else:
            text = self._dep_detail(row["raw"], row["verdict"])
        self.query_one("#scout-detail", Static).update(text)

    def _ai_detail(self, v: dict[str, Any], verdict: str) -> str:
        color = _VERDICT_COLORS.get(verdict, "#d9f7ff")
        fit_reasons = v.get("fit_reasons") or []
        unknowns = v.get("unknowns") or []
        lines = [
            f"[{color} bold]{verdict}[/]  [#d9f7ff]{v.get('tool_name', '—')}[/]",
            f"[#6e8aa1]category: {v.get('category', '—')}   fit: {v.get('fit', '—')}   risk: {v.get('risk', '—')}[/]",
            "",
            "[#d9f7ff bold]What[/]",
            f"  {v.get('what', '—')}",
            "",
            "[#d9f7ff bold]Why we suggest this[/]",
            f"  {v.get('why_it_matters', '—')}",
            "",
            "[#d9f7ff bold]Why it fits your repo[/]",
        ]
        if fit_reasons:
            for r in fit_reasons[:5]:
                lines.append(f"  · {r}")
        else:
            lines.append("  · seeded match; not personalised yet")
        lines.extend(
            [
                "",
                "[#d9f7ff bold]Risk reasoning[/]",
                f"  · risk level: {v.get('risk', '—')}",
            ]
        )
        if unknowns:
            for u in unknowns[:3]:
                lines.append(f"  · unknown: {u}")
        else:
            lines.append("  · no unknowns flagged")
        lines.extend(
            [
                "",
                "[#d9f7ff bold]Next safe step[/]",
                f"  {v.get('next_safe_step', '—')}",
                "",
                f"[#6e8aa1]source: {v.get('source_url', '—')}[/]",
            ]
        )
        return "\n".join(lines)

    def _dep_detail(self, f: dict[str, Any], verdict: str) -> str:
        color = _DEP_VERDICT_COLORS.get(verdict, "#d9f7ff")
        classification = f.get("classification", "—")
        evidence = f.get("evidence_quotes") or []
        advisories = f.get("advisory_ids") or []
        lines = [
            f"[{color} bold]{verdict}[/]  "
            f"[#d9f7ff]{f.get('package_name', '?')} "
            f"{f.get('from_version', '?')} → {f.get('to_version', '?')}[/]",
            f"[#6e8aa1]classification: {classification}   "
            f"repo_fit: {f.get('repo_fit', '—')}   "
            f"confidence: {f.get('classifier_confidence', '—')}[/]",
            "",
            "[#d9f7ff bold]Why this upgrade matters[/]",
        ]
        if evidence:
            for q in evidence[:3]:
                lines.append(f"  · {q}")
        else:
            lines.append(
                "  · no release-note evidence on file — classified by ecosystem heuristics"
            )
        lines.extend(
            [
                "",
                "[#d9f7ff bold]Severity[/]",
                f"  · {self._classification_to_risk(classification)}  "
                f"(classification: {classification})",
            ]
        )
        if advisories:
            lines.append(f"  · advisory IDs: {', '.join(advisories[:5])}")
        lines.extend(
            [
                "",
                "[#d9f7ff bold]Next safe step[/]",
                f"  {f.get('next_safe_step', 'frontier-scout deps trial …')}",
            ]
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _highlighted(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        table = self.query_one("#scout-table", DataTable)
        idx = table.cursor_row if table.cursor_row is not None else 0
        try:
            return self._rows[idx]
        except (IndexError, TypeError):
            return self._rows[0] if self._rows else None

    def action_primary_action(self) -> None:
        self._on_try()

    @on(Button.Pressed, "#scout-try")
    def _on_try(self) -> None:
        row = self._highlighted()
        if not row:
            self.app_ref.log_event("No findings yet — wait for the scout to populate.", tone="warn")
            return
        if row["kind"] == "ai":
            self._trial_ai(row["raw"])
        else:
            self._trial_dep(row["raw"])

    @work(thread=True, exclusive=True)
    def _trial_ai(self, v: dict[str, Any]) -> None:
        from frontier_scout.trials import run_trial

        stack = stack_from_profile(self.app_ref.diagnostics.profile)
        try:
            result = run_trial(
                v.get("tool_name", ""),
                url=v.get("source_url"),
                dry_run=True,
                stack=stack,
                repo=self.app_ref.diagnostics.repo,
            )
        except Exception as exc:  # noqa: BLE001
            self.app_ref.call_from_thread(
                self.app_ref.log_event,
                f"Trial failed for {v.get('tool_name', '?')}: {exc}",
                "error",
            )
            return
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Trial receipt for {result.get('tool_name')}: {result.get('receipt_path')}",
            "ok",
        )

    @work(thread=True, exclusive=True)
    def _trial_dep(self, f: dict[str, Any]) -> None:
        from frontier_scout.dep_trial import run_dependency_trial

        repo = Path(self.app_ref.diagnostics.repo)
        try:
            result = run_dependency_trial(
                f.get("package_name", ""),
                from_version=f.get("from_version", ""),
                to_version=f.get("to_version", ""),
                repo=repo,
                dry_run=True,
            )
        except Exception as exc:  # noqa: BLE001
            self.app_ref.call_from_thread(
                self.app_ref.log_event,
                f"Dep trial failed for {f.get('package_name', '?')}: {exc}",
                "error",
            )
            return
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Dep trial receipt for {result.get('tool_name')}: {result.get('receipt_path')}",
            "ok",
        )

    @on(Button.Pressed, "#scout-open")
    def _on_open(self) -> None:
        row = self._highlighted()
        if not row:
            return
        url = row.get("source_url")
        if not url:
            self.app_ref.log_event(
                "This finding has no canonical URL to open.", tone="warn"
            )
            return
        webbrowser.open(url)
        self.app_ref.log_event(f"Opened {url}", tone="info")

    @on(Button.Pressed, "#scout-dismiss")
    def _on_dismiss(self) -> None:
        row = self._highlighted()
        if not row:
            return
        tool = row.get("tool_name") or ""
        if not tool:
            return
        state = read_setup_state()
        dismissed = list(state.get("dismissed_tools") or [])
        if tool not in dismissed:
            dismissed.append(tool)
            state["dismissed_tools"] = dismissed
            write_setup_state(state)
        self._rows = [r for r in self._rows if r.get("tool_name") != tool]
        table = self.query_one("#scout-table", DataTable)
        table.clear()
        for r in self._rows:
            color = _VERDICT_COLORS.get(r["verdict"], "#6e8aa1")
            table.add_row(
                f"[{color} bold]{r['verdict']}[/]",
                r["tool_name"],
                r["fit"],
                r["risk"],
                r["category"],
            )
        if self._rows:
            table.cursor_coordinate = (0, 0)
            self._render_detail(self._rows[0])
        else:
            self._render_empty()
        # Keep the header count in sync with the visible rows.
        status = self.query_one("#scout-status", Static)
        status.update(f"[#6e8aa1]· {len(self._rows)} finding(s) · press [s] to rescout[/]")
        self.app_ref.log_event(f"Dismissed {tool}.", tone="warn")

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    def action_rescout(self) -> None:
        self.app_ref.log_event("Rescouting…", tone="info")
        self._scout_worker()

    def action_clear_memory(self) -> None:
        from frontier_scout.store import clear_scans_for_repo

        repo = self.app_ref.diagnostics.repo
        removed = clear_scans_for_repo(repo)
        # Also clear dismissals so the user sees a clean state.
        state = read_setup_state()
        state["dismissed_tools"] = []
        write_setup_state(state)
        self.app_ref.log_event(
            f"Cleared {removed} stored scan(s) for this repo. Dismissals reset.",
            tone="warn",
        )
        self._scout_worker()
