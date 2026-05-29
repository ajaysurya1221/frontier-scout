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

    /* Stream L — adaptive layout for embedded terminals (VS Code,
       tmux split, etc.). ``.compact`` is added by SetupApp.on_resize
       whenever the viewport falls below 100x24 so the table doesn't
       eat the entire visible area. */
    ScoutTab.compact .scout-controls {
        height: auto;
        margin-bottom: 0;
    }

    ScoutTab.compact DataTable {
        height: 8;
    }

    ScoutTab.compact #scout-detail {
        margin-top: 0;
        max-height: 14;
    }
    """

    BINDINGS: ClassVar = [
        Binding("s", "rescout", "Rescout", show=True),
        Binding("c", "clear_memory", "Clear memory", show=True),
        Binding("enter", "primary_action", "Try locally", show=True),
        # Stream M — full TUI surface for the CLI capabilities the
        # user previously had to drop to a shell for.
        Binding("L", "lab_selected", "Lab (2× to spend)", show=True),
        Binding("e", "evaluate_selected", "Evaluate", show=True),
        Binding("D", "dossier_selected", "Dossier", show=True),
    ]

    #: Double-press window for the live-lab confirmation. Mirrors the
    #: existing live-scout double-press pattern in v1.1.
    _LAB_LIVE_CONFIRM_WINDOW_S = 3.0

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._rows: list[dict[str, Any]] = []
        self._guard_findings: list = []
        state = read_setup_state()
        self._scope_ai = bool(state.get("scout_scope_ai", True))
        self._scope_deps = bool(state.get("scout_scope_deps", True))
        # Stream M — remember the last time the user pressed L, so a
        # second press within the confirmation window upgrades to a
        # real (live) lab run instead of just classifying.
        self._last_lab_press: float = 0.0

    # ------------------------------------------------------------------
    # Compose / mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # v1.3.0 Stream C — explicit primary action button. No more
        # auto-fire on mount; the user always knows they triggered it.
        with Horizontal(classes="scout-controls"):
            yield Button(
                "▶ Scout now  (s)",
                id="scout-run",
                variant="success",
            )
            yield Button(self._scope_label("ai"), id="scout-toggle-ai", classes=self._scope_class("ai"))
            yield Button(self._scope_label("deps"), id="scout-toggle-deps", classes=self._scope_class("deps"))
            yield Static("", id="scout-status")
        yield Static("", id="scout-guard-banner", classes="hidden", markup=True)
        yield DataTable(id="scout-table", cursor_type="row", zebra_stripes=True)
        # v1.3.0 Stream C — every action visible. Bindings stay for
        # power users; buttons exist so newcomers can discover what's
        # possible without reading docs.
        with Horizontal(classes="scout-controls"):
            yield Button("Try locally  (Enter)", id="scout-try")
            yield Button("Lab  (L)", id="scout-lab")
            yield Button("Evaluate  (e)", id="scout-evaluate")
            yield Button("Dossier  (D)", id="scout-dossier")
            yield Button("Open URL", id="scout-open")
            yield Button("Dismiss", id="scout-dismiss")
        yield Static(
            (
                "[#6e8aa1]Press [bold]▶ Scout now[/bold] above (or [bold]s[/bold]) "
                "to look for AI tools and dependency upgrades that fit your repo. "
                "Each row carries fit, risk, and concerns so you know why we flagged it. "
                "Press [bold]?[/bold] for a glossary of every term.[/]"
            ),
            id="scout-detail",
            markup=True,
        )

    def on_mount(self) -> None:
        table = self.query_one("#scout-table", DataTable)
        # v1.3.0 Stream C — added Concerns column so concern chips are
        # visible at a glance, not buried in the detail panel.
        table.add_columns(
            "Verdict", "Tool / Package", "Fit", "Risk", "Concerns", "Category"
        )
        # v1.3.0 Stream C — no auto-fire. User clicks ▶ Scout now or
        # presses s. We DO NOT call .focus() here because focusing a
        # widget inside a TabbedContent pane forcibly activates that
        # pane, which breaks `--tab settings` on launch. Instead the
        # button gets the success variant so it visually advertises
        # as the primary action without dragging focus.

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

    @on(Button.Pressed, "#scout-run")
    def _on_run_button(self) -> None:
        """v1.3.0 Stream C — primary action. Same path as `s`."""

        self._scout_worker()

    @on(Button.Pressed, "#scout-toggle-ai")
    def _toggle_ai(self) -> None:
        self._scope_ai = not self._scope_ai
        self._persist_scope()
        self._refresh_scope_buttons()
        # v1.3.0 — toggles are now persistence-only; user re-runs with
        # ▶ Scout now. Avoids surprise scouts on every click.

    @on(Button.Pressed, "#scout-toggle-deps")
    def _toggle_deps(self) -> None:
        self._scope_deps = not self._scope_deps
        self._persist_scope()
        self._refresh_scope_buttons()
        # See note above; toggle doesn't auto-rerun.

    @on(Button.Pressed, "#scout-lab")
    def _on_lab_button(self) -> None:
        self.action_lab_selected()

    @on(Button.Pressed, "#scout-evaluate")
    def _on_evaluate_button(self) -> None:
        self.action_evaluate_selected()

    @on(Button.Pressed, "#scout-dossier")
    def _on_dossier_button(self) -> None:
        self.action_dossier_selected()

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

    def _build_progress_reporter(self):
        """v1.3.0 Stream C — return a TuiProgressReporter wired to the
        shell's StatusStrip + ProgressStrip, or NullReporter if either
        sink isn't mounted (e.g. very early startup). The shell adds
        these widgets in v1.3.0 Stream B."""

        from frontier_scout.progress import NullReporter
        from frontier_scout.tui.progress_view import (
            ProgressStrip,
            StatusStrip,
            TuiProgressReporter,
        )

        try:
            status = self.app_ref.query_one(StatusStrip)
        except Exception:  # noqa: BLE001
            status = None
        try:
            bar = self.app_ref.query_one(ProgressStrip)
        except Exception:  # noqa: BLE001
            bar = None
        if status is None and bar is None:
            return NullReporter()
        return TuiProgressReporter(
            app=self.app_ref,
            status=status,
            bar=bar,
            log_event=self.app_ref.log_event,
        )

    @work(thread=True, exclusive=True)
    def _scout_worker(self) -> None:
        from frontier_scout.scout import run_scan

        progress = self._build_progress_reporter()
        repo = Path(self.app_ref.diagnostics.repo)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        # Stream J — universal mode skips the repo-profile filter and
        # surfaces every seeded verdict. We also don't persist a scan
        # row for a non-repo so the SQLite table stays repo-scoped.
        universal = bool(getattr(self.app_ref, "universal_mode", False))

        if self._scope_ai:
            try:
                payload = run_scan(
                    repo=repo,
                    dry_run=True,
                    persist=not universal,
                    reporter=progress,
                )
                for v in payload.get("verdicts") or []:
                    rows.append(self._ai_verdict_to_row(v))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"AI scan failed: {exc}")

        if self._scope_deps:
            try:
                from frontier_scout.dependencies import run_dependency_scan

                payload = run_dependency_scan(repo, persist=False, reporter=progress)
                for f in payload.get("findings") or []:
                    row = self._dep_finding_to_row(f)
                    if row is not None:
                        rows.append(row)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Dependency scan failed: {exc}")

        guard_findings: list = []
        try:
            from frontier_scout.guard import run_guard

            guard_findings = run_guard(repo, reporter=progress) or []
        except Exception:
            guard_findings = []

        # v1.3.0 Stream C — explicit completion signal so the status
        # strip resets to "Ready" instead of holding the last stage.
        try:
            progress.finish(
                f"Scout complete · {len(rows)} finding(s) · "
                f"{len(guard_findings)} guard alert(s)"
            )
        except AttributeError:
            # NullReporter has no .finish; ignore.
            pass

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
                    self._concerns_cell(r),
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
            "[dim]nothing found yet — press [bold]▶ Scout now[/] (or [bold]s[/]) above[/]",
            "[dim]—[/]",
            "[dim]—[/]",
            "[dim]—[/]",
            "[dim]—[/]",
        )
        self.query_one("#scout-detail", Static).update(
            "[#6e8aa1]Nothing to show yet. Press [bold]▶ Scout now[/] (or [bold]s[/]) "
            "to scan, or toggle a scope above. The button is focused — Enter triggers it.[/]"
        )

    def _concerns_cell(self, row: dict[str, Any]) -> str:
        """v1.3.0 Stream C — render the verdict's concerns as a small
        coloured chip: ``● count`` where the dot colour matches the
        highest-severity concern present. Empty list renders as a
        muted dash so the column never looks broken."""

        raw = row.get("raw") or {}
        concerns = raw.get("concerns") or []
        if not concerns:
            return "[#6e8aa1]—[/]"
        severities = {c.get("severity", "low") for c in concerns}
        if "high" in severities:
            colour = "#ff6b6b"
        elif "medium" in severities:
            colour = "#e3c26f"
        else:
            colour = "#7aa6ff"
        return f"[{colour}]● {len(concerns)}[/]"

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
        concerns = v.get("concerns") or []
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
        # Stream K — the centerpiece. Show concerns prominently so
        # the user always knows why we'd push back on adoption.
        if concerns:
            lines.extend(["", "[#d9f7ff bold]Concerns[/]"])
            severity_color = {
                "high": "#ff6b6b",
                "medium": "#e3c26f",
                "low": "#7aa6ff",
            }
            for c in concerns[:6]:
                slug_color = severity_color.get(c.get("severity", "low"), "#6e8aa1")
                label = c.get("label", c.get("slug", "?"))
                evidence = c.get("evidence", "")
                lines.append(f"  [{slug_color}]●[/] [bold]{label}[/] — {evidence}")
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
                self._concerns_cell(r),
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

    # ------------------------------------------------------------------
    # Stream M — lab / evaluate / dossier from a Scout row
    # ------------------------------------------------------------------

    def action_lab_selected(self) -> None:
        """L → dry-run lab. Second L within the confirm window → live lab.

        Mirrors the v1.1 ``live`` scout double-press: first press is
        free, second press within ``_LAB_LIVE_CONFIRM_WINDOW_S`` runs
        the real hermetic install and spends API quota.
        """

        import time

        row = self._highlighted()
        if not row:
            self.app_ref.log_event(
                "No row highlighted — pick a verdict first.", tone="warn"
            )
            return
        if row["kind"] != "ai":
            self.app_ref.log_event(
                "Lab only runs against AI-tool rows; pick a tool, not a dep.",
                tone="warn",
            )
            return
        v = row["raw"]
        tool = v.get("tool_name", "")
        url = v.get("source_url")
        if not url:
            self.app_ref.log_event(
                f"{tool}: no source URL on this verdict — can't lab it.",
                tone="warn",
            )
            return
        now = time.monotonic()
        live = (now - self._last_lab_press) < self._LAB_LIVE_CONFIRM_WINDOW_S
        self._last_lab_press = 0.0 if live else now
        if not live:
            self.app_ref.log_event(
                f"L → dry-run lab for {tool}. Press L again within "
                f"{self._LAB_LIVE_CONFIRM_WINDOW_S:.0f}s to spend on a live "
                "install.",
                tone="info",
            )
        self._lab_worker(tool=tool, url=url, live=live)

    @work(thread=True, exclusive=True)
    def _lab_worker(self, *, tool: str, url: str, live: bool) -> None:
        try:
            import importlib
            import sys
            from pathlib import Path

            scripts_dir = (
                Path(__file__).resolve().parent.parent.parent.parent / "scripts"
            )
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            lab_runner = importlib.import_module("lab_runner")
            rc = lab_runner.run(tool, url, user="", dry_run=not live)
        except Exception as exc:  # noqa: BLE001
            self.app_ref.call_from_thread(
                self.app_ref.log_event,
                f"Lab failed for {tool}: {exc}",
                "error",
            )
            return
        tone = "ok" if rc == 0 else "warn"
        verb = "lab" if live else "dry-run lab"
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"{verb} {tool}: rc={rc} (receipt in ~/.frontier-scout/labs/)",
            tone,
        )

    def action_evaluate_selected(self) -> None:
        """e → run the Adoption Firewall evaluation on the highlighted
        verdict's source URL and write the decision to the log."""

        row = self._highlighted()
        if not row or row["kind"] != "ai":
            self.app_ref.log_event(
                "Evaluate needs an AI-tool row highlighted.", tone="warn"
            )
            return
        v = row["raw"]
        url = v.get("source_url")
        if not url:
            self.app_ref.log_event(
                f"{v.get('tool_name', '?')}: no URL to evaluate.", tone="warn"
            )
            return
        self._evaluate_worker(url=url, tool=v.get("tool_name", "?"))

    @work(thread=True, exclusive=True)
    def _evaluate_worker(self, *, url: str, tool: str) -> None:
        try:
            from pathlib import Path

            from frontier_scout.evaluate import evaluate_url
            from frontier_scout.mcp_audit import classify_mcp_capabilities
            from frontier_scout.policy import evaluate_policy, load_policy
            from frontier_scout.scout import detect_stack

            repo = Path(self.app_ref.diagnostics.repo)
            stack = detect_stack(repo)
            evaluation = evaluate_url(url, stack)
            manifest = (
                evaluation.permission_manifest
                or classify_mcp_capabilities(
                    url,
                    tool_name=evaluation.tool_name,
                    source_url=url,
                )
            )
            policy = load_policy(repo)
            decision = evaluate_policy(evaluation, manifest, policy=policy)
        except Exception as exc:  # noqa: BLE001
            self.app_ref.call_from_thread(
                self.app_ref.log_event,
                f"Evaluate failed for {tool}: {exc}",
                "error",
            )
            return
        verdict_str = str(decision.verdict).upper()
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Evaluate {tool}: {verdict_str} — {decision.summary}",
            "ok" if verdict_str == "ADOPT" else "info",
        )

    def action_dossier_selected(self) -> None:
        """D → build a dossier for the highlighted tool, save it, open it."""

        row = self._highlighted()
        if not row or row["kind"] != "ai":
            self.app_ref.log_event(
                "Dossier needs an AI-tool row highlighted.", tone="warn"
            )
            return
        tool = row["raw"].get("tool_name", "")
        if not tool:
            return
        self._dossier_worker(tool=tool)

    @work(thread=True, exclusive=True)
    def _dossier_worker(self, *, tool: str) -> None:
        try:
            from pathlib import Path

            from frontier_scout.dossier import build_dossier
            from frontier_scout.store import home_dir

            repo = Path(self.app_ref.diagnostics.repo)
            payload = build_dossier(tool, repo=repo)
            target_dir = home_dir() / "dossiers"
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = "".join(
                ch if ch.isalnum() or ch in "-_" else "-" for ch in tool
            ).strip("-").lower() or "tool"
            target_path = target_dir / f"{safe_name}.json"
            import json

            target_path.write_text(json.dumps(payload, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            self.app_ref.call_from_thread(
                self.app_ref.log_event,
                f"Dossier failed for {tool}: {exc}",
                "error",
            )
            return
        self.app_ref.call_from_thread(
            self.app_ref.log_event,
            f"Dossier for {tool} → {target_path}",
            "ok",
        )
