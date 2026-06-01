"""Mission Control (tui3) — the responsive app shell.

A single Textual app: header · body (rail + tabstrip + main + floor) · compass,
plus modal overlays. Everything is composed ONCE; reflow is done by toggling
``display`` and updating markup — never by tearing widgets down and re-mounting
them (which races Textual's deferred removal). Only the active pane's content is
swapped, with an awaited removal so IDs never collide.

The body reflows by breakpoint (tiny floor / micro / narrow / mid / wide),
recomputed on every resize, so the UI never breaks at any terminal size. A
background worker bridges scout.run_scan to the UI via Progress/WorkDone/
WorkFailed (mirrors the proven tui2 bridge).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from frontier_scout.tui3 import data
from frontier_scout.tui3.kit import MIN_COLS, MIN_ROWS, breakpoint_for, glyphs, mono
from frontier_scout.tui3.messages import Progress, TuiReporter, WorkDone, WorkFailed
from frontier_scout.tui3.state import AppState
from frontier_scout.tui3.widgets import ClickStatic

# Tab registry: (id, label, short). Incident dropped (no backend) — decision D1.
TABS: list[tuple[str, str, str]] = [
    ("scout", "Scout", "Scout"),
    ("schedule", "Schedule", "Sched"),
    ("receipts", "Receipts", "Rcpts"),
    ("guard", "Guard", "Guard"),
    ("packs", "Packs", "Packs"),
    ("deps", "Deps", "Deps"),
    ("reports", "Reports", "Rprt"),
    ("settings", "Settings", "Set"),
]
TAB_IDS = [t[0] for t in TABS]


class MissionControlApp(App[int]):
    """Frontier Scout — Mission Control."""

    CSS_PATH = "theme.tcss"
    TITLE = "Frontier Scout · Mission Control"

    BINDINGS = [
        Binding("q", "quit", "quit", show=False),
        Binding("question_mark", "help", "help", show=False),
        Binding("n", "notifications", "notifications", show=False),
        Binding("u", "toggle_unicode", "unicode/ascii", show=False),
        Binding("c", "toggle_color", "color/mono", show=False),
        Binding("s", "scout_now", "scout", show=False),
        Binding("g", "guard_shortcut", "guard", show=False),
        Binding("r", "refresh", "refresh", show=False),
        Binding("p", "palette", "palette", show=False),
        Binding("w", "switch_repo", "switch repo", show=False),
        *[Binding(str(i + 1), f"goto_{t}", t, show=False) for i, (t, _, _) in enumerate(TABS)],
        Binding("j,down", "move(1)", "down", show=False),
        Binding("k,up", "move(-1)", "up", show=False),
        Binding("right", "scope(1)", "scope", show=False),
        Binding("left", "scope(-1)", "scope", show=False),
        Binding("a", "ask", "ask", show=False),
        Binding("D", "dossier", "dossier", show=False),
        Binding("i", "implement", "implement&test", show=False),
        Binding("e", "evaluate", "evaluate", show=False),
        Binding("L", "lab", "lab", show=False),
        Binding("X", "clear_history", "clear history", show=False),
        Binding("R", "reconfigure", "reconfigure", show=False),
        Binding("enter", "primary", "primary", show=False),
        Binding("o", "open_target", "open", show=False),
        Binding("d", "discover", "discover", show=False),
        Binding("t", "toggle_schedule", "toggle", show=False),
        Binding("delete,backspace", "remove_schedule", "remove", show=False),
        Binding("N", "new_schedule", "new schedule", show=False),
        Binding("E", "edit_schedule", "edit schedule", show=False),
    ]

    SCOPES = ["all", "ai-devtools", "mcp", "deps"]

    def __init__(self, *, repo: Path | None = None, demo: bool = False) -> None:
        super().__init__()
        self._repo = repo or Path(".")
        self._demo = demo
        self.state = AppState()
        self._bp_name = ""
        self._scanning = False
        self._size_override: tuple[int, int] | None = None
        self._ask_i = 0
        # Path of the last rendered briefing.html (set by the report worker);
        # the Reports tab's "open" action reuses it instead of re-rendering.
        self._last_report_html: str | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Static(id="mc-header")
        with Container(id="mc-body"):
            # Rail/tabstrip are per-tab ClickStatic cells (one clickable widget
            # per tab — handoff §5), repainted in place on reflow (never remounted,
            # so no DuplicateIds — Bug #3). Both are composed once; display is
            # toggled by breakpoint. Each cell click routes to the same _goto the
            # number keys use.
            with Vertical(id="mc-rail"):
                yield Static("", classes="rail-brand", id="rail-brand")
                for tid, _label, _short in TABS:
                    yield ClickStatic(
                        "", lambda t=tid: self.call_later(self._goto, t),
                        id=f"rail-{tid}", classes="rtab")
            with Horizontal(id="mc-tabstrip"):
                for tid, _label, _short in TABS:
                    yield ClickStatic(
                        "", lambda t=tid: self.call_later(self._goto, t),
                        id=f"strip-{tid}", classes="ts")
            yield VerticalScroll(id="mc-main")
            yield Static(id="mc-floor")
        yield Static(id="mc-compass")

    async def on_mount(self) -> None:
        self.state = data.initial_state(self._repo, demo=self._demo)
        await self._render()

    # ── responsive core ──────────────────────────────────────────────────────
    @property
    def _term_size(self) -> tuple[int, int]:
        # Prefer the size carried by the last Resize event: Textual's self.size
        # can lag one event behind during rapid/live resizes.
        if self._size_override is not None:
            return self._size_override
        sz = self.size
        w, h = sz.width, sz.height
        if w <= 1 or h <= 1:
            # Container not laid out yet (e.g. the very first paint before the
            # first Resize event). Fall back to the real terminal size from the
            # driver, never to the "too small" floor (handoff measurement note).
            try:
                cs = self.console.size
                w, h = cs.width, cs.height
            except Exception:  # noqa: BLE001
                w, h = 80, 24
        return max(1, w), max(1, h)

    async def on_resize(self, event: Any = None) -> None:
        size = getattr(event, "size", None)
        if size is not None:
            self._size_override = (max(1, size.width), max(1, size.height))
        bp = breakpoint_for(*self._term_size)
        if bp.name != self._bp_name:
            await self._render()
        else:
            self._refresh_chrome()

    async def _render(self) -> None:
        """Reflow chrome for the current breakpoint and (re)render the pane.

        Compose-once: we only toggle display + update markup here; the single
        pane swap awaits removal so nothing collides.
        """
        cols, rows = self._term_size
        bp = breakpoint_for(cols, rows)
        self._bp_name = bp.name

        try:
            body = self.query_one("#mc-body", Container)
            rail = self.query_one("#mc-rail", Vertical)
            strip = self.query_one("#mc-tabstrip", Horizontal)
            main = self.query_one("#mc-main", VerticalScroll)
            floor = self.query_one("#mc-floor", Static)
        except Exception:  # noqa: BLE001 — pre-mount
            return

        for name in ("tiny", "micro", "narrow", "mid", "wide"):
            self.screen.set_class(name == bp.name, f"-{name}")
        body.set_class(bp.rail, "row")
        body.set_class(not bp.rail, "col")

        tiny = bp.name == "tiny"
        rail.display = bp.rail and not tiny
        strip.display = (not bp.rail) and not tiny
        main.display = not tiny
        floor.display = tiny

        if tiny:
            floor.update(self._paint(self._floor_text()))
            self._refresh_chrome()
            return

        rail.set_class(bp.rail_compact, "compact")
        self._paint_nav()

        await self._render_pane()
        self._refresh_chrome()

    async def _render_pane(self) -> None:
        try:
            main = self.query_one("#mc-main", VerticalScroll)
        except Exception:  # noqa: BLE001
            return
        await main.remove_children()
        await main.mount(self._build_pane(self.state.tab))

    def _refresh_chrome(self) -> None:
        self._set("#mc-header", self._header_text())
        self._set("#mc-compass", self._compass_text())

    def _refresh_nav(self) -> None:
        """Repaint rail + tabstrip cells in place (e.g. after a tab change)."""
        self._paint_nav()

    def _paint(self, markup: str) -> str:
        """Apply the color fallback: pass markup through, or strip color in mono."""
        return markup if self.state.color else mono(markup)

    def _set(self, selector: str, markup: str) -> None:
        """Update a Static's content, painted for the current color mode."""
        try:
            self.query_one(selector, Static).update(self._paint(markup))
        except Exception:  # noqa: BLE001 — widget may not be mounted yet
            pass

    # ── chrome renderers (all return Rich markup strings) ────────────────────
    def _header_text(self) -> str:
        g = glyphs(self.state.unicode)
        cols, _ = self._term_size
        micro = self._bp_name == "micro"
        left = f"[#24d6a8]{g['radar_core']}[/] "
        if not micro:
            left += "[#d9f7ff b]frontier scout[/] [#25405c]" + g["vbar"] + "[/] "
        left += f"[#a9bccd]{self.state.repo_name}[/]"
        if not micro:
            prov = self.state.provider
            if " " in prov:
                prov = prov.split(" ", 1)[0].lower()
            left += f"  [#6e8aa1]{g['dot']} {prov}[/]"
        right = ""
        if not micro:
            right += f"[#6e8aa1]{self.state.funnel.scanned} src {g['pip']} {self.state.funnel.window}[/]  "
        bell = f"[#24d6a8]{g['dot']}[/]" + (f"[#ff6b6b] {self.state.unread}[/]" if self.state.unread else "")
        pad = max(1, cols - _vis_len(left) - _vis_len(right) - _vis_len(bell) - 2)
        return left + " " * pad + right + bell

    def _compass_text(self) -> str:
        g = glyphs(self.state.unicode)
        bp = self._bp_name
        if bp == "micro":
            hints = [("1-8", "tabs"), ("?", "help"), ("q", "quit")]
        elif bp == "narrow":
            hints = [("1-8", "tabs"), ("j/k", "move"), ("s", "scout"), ("?", "help"), ("q", "quit")]
        else:
            hints = [
                ("1-8", "tabs"), (f"j/k {g['ud']}", "move"), (g["enter"], "open"),
                (g["lr"], "swipe"), ("a", "ask"), ("s", "scout"),
                (f"{g['cmd']}K", "palette"), ("u/c", "ascii/mono"), ("?", "help"), ("q", "quit"),
            ]
        # Tab-contextual hint: the Reports tab's primary/open actions (⏎ render ·
        # o open). Skipped at micro width, where the compass already drops hints.
        if self.state.tab == "reports" and bp != "micro":
            hints = [(g["enter"], "render"), ("o", "open"), *hints]
        # Packs: ⏎ refresh (offline) · d discover (network gate).
        elif self.state.tab == "packs" and bp != "micro":
            hints = [(g["enter"], "refresh"), ("d", "discover"), *hints]
        # Schedule: j/k select · ⏎ run · t toggle · del remove · N new · E edit.
        # The create/edit hints are only shown from "narrow" up (skipped on the
        # already-trimmed micro compass) so the line stays readable.
        elif self.state.tab == "schedule" and bp != "micro":
            sched_hints = [
                ("j/k", "select"), (g["enter"], "run"),
                ("t", "toggle"), ("del", "remove"),
            ]
            if bp != "narrow":
                sched_hints += [("N", "new"), ("E", "edit")]
            hints = [*sched_hints, *hints]
        # Deps/Guard: surface the r-scan affordance in the compass so the "Press
        # r" empty-state has a live keymap echo (prototype fs2-app.jsx:147-148).
        elif self.state.tab == "deps" and bp != "micro":
            hints = [("r", "scan"), *hints]
        elif self.state.tab == "guard" and bp != "micro":
            hints = [("r", "re-run"), *hints]
        parts = " ".join(f"[#24d6a8 b]{k}[/][#6e8aa1] {label}[/]" for k, label in hints)
        if self._scanning:
            tail = "[#24d6a8]scanning…[/]"
        else:
            tail = f"[#6e8aa1]{len(self.state.verdicts)} verdicts {g['pip']} ${self.state.funnel.cost:.2f}[/]"
        cols, _ = self._term_size
        pad = max(1, cols - _vis_len(parts) - _vis_len(tail) - 2)
        return parts + " " * pad + tail

    def _paint_nav(self) -> None:
        """Repaint the per-tab rail + tabstrip cells in place (no remount)."""
        bp = breakpoint_for(*self._term_size)
        g = glyphs(self.state.unicode)
        compact = bp.rail_compact
        brand = g["radar_core"] if compact else f"{g['radar_core']} [#d9f7ff b]scout[/]"
        self._set("#rail-brand", brand)
        for i, (tid, label, short) in enumerate(TABS):
            on = tid == self.state.tab
            if compact:
                rcell = f"{i + 1}"
            else:
                badge = self._badge(tid)
                btxt = f"  {badge}" if badge else ""
                rcell = f"{i + 1} {label}{btxt}"
            self._set_cell(
                f"#rail-{tid}",
                f"[#d9f7ff b on #10202a]{rcell}[/]" if on else f"[#6e8aa1]{rcell}[/]")
            scell = f"{i + 1}" if bp.numeric_tabs else f"{i + 1}{short}"
            self._set_cell(
                f"#strip-{tid}",
                f"[#24d6a8 b]{scell}[/]" if on else f"[#6e8aa1]{scell}[/]")

    def _set_cell(self, selector: str, markup: str) -> None:
        try:
            self.query_one(selector, ClickStatic).update(self._paint(markup))
        except Exception:  # noqa: BLE001 — widget may not be mounted yet
            pass

    def _floor_text(self) -> str:
        g = glyphs(self.state.unicode)
        cols, rows = self._term_size
        ok_w = cols >= MIN_COLS
        ok_h = rows >= MIN_ROWS
        wmark = ("[#24d6a8]" + g["check"] if ok_w else "[#ff6b6b]" + g["cross"]) + f" width {cols}/{MIN_COLS}[/]"
        hmark = ("[#24d6a8]" + g["check"] if ok_h else "[#ff6b6b]" + g["cross"]) + f" height {rows}/{MIN_ROWS}[/]"
        return (
            f"[#e3c26f]{g['diamond']}[/]\n"
            f"[#d9f7ff b]TERMINAL TOO SMALL[/]\n\n"
            f"[#6e8aa1]Mission Control needs at least {MIN_COLS}×{MIN_ROWS}.\n"
            f"Now: {cols}×{rows}. Resize the window to continue.[/]\n\n"
            f"{wmark}   {hmark}"
        )

    def _badge(self, tid: str) -> str:
        if tid == "scout":
            return str(len(self.state.verdicts)) if self.state.verdicts else ""
        return ""

    def _build_pane(self, tab: str):
        from frontier_scout.tui3.panes import build_pane

        return build_pane(self, tab)

    # ── actions ──────────────────────────────────────────────────────────────
    async def _goto(self, tab: str) -> None:
        if tab != self.state.tab:
            self.state = self.state.with_(tab=tab, sel=0)
            self._refresh_nav()
            await self._render_pane()
            if tab == "guard" and self.state.guard_cache is None:
                self._refresh_worker("guard")
            elif tab == "deps" and self.state.deps_cache is None:
                self._refresh_worker("deps")
            elif tab == "settings" and self.state.settings_cache is None:
                self._refresh_worker("settings")
            self._refresh_chrome()

    async def action_goto_scout(self) -> None: await self._goto("scout")
    async def action_goto_schedule(self) -> None: await self._goto("schedule")
    async def action_goto_receipts(self) -> None: await self._goto("receipts")
    async def action_goto_guard(self) -> None: await self._goto("guard")
    async def action_goto_packs(self) -> None: await self._goto("packs")
    async def action_goto_deps(self) -> None: await self._goto("deps")
    async def action_goto_reports(self) -> None: await self._goto("reports")
    async def action_goto_settings(self) -> None: await self._goto("settings")
    async def action_guard_shortcut(self) -> None: await self._goto("guard")

    def _select(self, i: int) -> None:
        """Select a verdict by scoped index — click parity for j/k."""
        self.state = self.state.with_(sel=i)
        self.call_later(self._render_pane)

    def _set_scope(self, scope: str) -> None:
        """Set the scout scope — click parity for ←/→."""
        if scope != self.state.scope:
            self.state = self.state.with_(scope=scope, sel=0)
            self.call_later(self._render_pane)

    def _select_sched(self, i: int) -> None:
        """Select a schedule row by index — click parity for j/k on schedule."""
        self.state = self.state.with_(sched_sel=i)
        self.call_later(self._render_pane)

    async def action_move(self, delta: int) -> None:
        if self.state.tab == "scout" and self.state.verdicts:
            self.state = self.state.move(delta)
            self._refresh_nav()
            await self._render_pane()
        elif self.state.tab == "schedule":
            rows = data.schedules()
            if not rows:
                return
            nxt = max(0, min(len(rows) - 1, self.state.sched_sel + delta))
            self.state = self.state.with_(sched_sel=nxt)
            await self._render_pane()

    async def action_scope(self, delta: int) -> None:
        """Cycle the Scout scope chip (all / ai-devtools / mcp / deps)."""
        if self.state.tab != "scout":
            return
        order = self.SCOPES
        try:
            i = order.index(self.state.scope)
        except ValueError:
            i = 0
        self.state = self.state.with_(scope=order[(i + delta) % len(order)], sel=0)
        await self._render_pane()
        self._refresh_chrome()

    async def action_ask(self) -> None:
        """Cycle the offline Ask question for the selected verdict (never spends)."""
        if self.state.tab == "scout" and self.state.verdicts:
            self._ask_i += 1
            await self._render_pane()

    # ── Per-tab primary / open (⏎ / o) — FREE, no spend, no gate ──────────────
    async def action_primary(self) -> None:
        """The per-tab primary action (⏎). Dispatch by the active tab.

        Reports → render the latest stored scan (FREE). Packs → refresh pack
        candidates from their seed definitions (FREE + LOCAL + offline — a safe
        local write, no gate; the network ``discover`` path is on ``d`` instead).
        Every other tab is an explicit no-op. Always no-op-safe: never raises
        when there is no repo / no current verdict / nothing to render.
        """
        tab = self.state.tab
        if tab == "reports":
            self._report_worker()
        elif tab == "packs":
            # Offline refresh: seed candidates only, guaranteed no network.
            self._packs_refresh_worker(discover=False)
        elif tab == "schedule":
            await self._schedule_primary()
        # Other tabs: intentional no-op (future increments extend this).

    async def _schedule_primary(self) -> None:
        """Run the selected schedule (⏎). The ONLY schedule spend path.

        ``dry_run`` is true when the app is in demo mode OR the schedule is not
        marked ``live`` — and that is exactly when running is free (seeded, no
        network, no spend), so it starts immediately with no gate. A LIVE
        schedule outside demo would spend, so it is held behind an explicit
        cost-confirm: nothing reaches the judge until the user clears it.
        No-op-safe: returns quietly when there are no schedules.
        """
        rows = data.schedules()
        if not rows:
            return
        idx = min(max(0, self.state.sched_sel), len(rows) - 1)
        sched = rows[idx]
        sched_id = str(sched["id"])
        repo = str(sched["repo"]).split("/")[-1]
        dry_run = self.state.demo or (not sched["live"])
        if not dry_run:
            from frontier_scout.tui3.overlays import ConfirmScreen

            def _on_confirm() -> None:
                self._schedule_run_worker(sched_id, dry_run=False)

            self.push_screen(
                ConfirmScreen(
                    "Run live scan",
                    [
                        f"[#e3c26f]Runs a LIVE scout for {repo} — calls the "
                        "judge, costs money.[/]",
                        "[#6e8aa1]The schedule is marked live scan.[/]",
                    ],
                    _on_confirm,
                    confirm_label="run live",
                )
            )
        else:
            self._schedule_run_worker(sched_id, dry_run=True)

    def _schedule_run_worker(self, schedule_id: str, *, dry_run: bool) -> None:
        """Run a schedule on a worker thread (mirrors ``_evaluate_worker``).

        ``dry_run`` is passed straight through to ``data.schedule_run`` — the
        gate decision was already made by ``_schedule_primary``; this method
        never re-decides it.
        """
        def _run() -> None:
            try:
                payload = data.schedule_run(schedule_id, dry_run=dry_run)
                self.post_message(WorkDone("schedule_run", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("schedule_run", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="schedule-run")

    # ── Schedule: toggle (t, FREE) · remove (del, FREE) ───────────────────────
    async def action_toggle_schedule(self) -> None:
        """Enable/disable the selected schedule (t) — FREE local JSON write.

        Schedule tab only. No gate: flipping ``disabled`` never spends, never
        reaches the network. Re-renders the pane so the on/off badge updates.
        No-op-safe when there are no schedules / wrong tab.
        """
        if self.state.tab != "schedule":
            return
        rows = data.schedules()
        if not rows:
            return
        idx = min(max(0, self.state.sched_sel), len(rows) - 1)
        result = data.schedule_toggle(str(rows[idx]["id"]))
        if self.state.tab == "schedule":
            await self._render_pane()
        # Toast the REAL new state so the keypress visibly "lands". On a failed
        # toggle ``disabled`` is absent — say so rather than implying success.
        try:
            if result.get("ok"):
                disabled = bool(result.get("disabled"))
                self.notify(f"schedule {'disabled' if disabled else 'enabled'}")
            else:
                self.notify("could not toggle schedule", severity="warning")
        except Exception:  # noqa: BLE001 — toast is best-effort feedback only
            self._set("#mc-compass", self._compass_text())

    async def action_remove_schedule(self) -> None:
        """Remove the selected schedule (del/backspace) — FREE, simple confirm.

        Schedule tab only. A removal is a cheap local JSON delete, so it uses a
        simple y-confirm (not a typed gate). Re-renders the pane afterwards so
        the row disappears. No-op-safe when there are no schedules / wrong tab.
        """
        if self.state.tab != "schedule":
            return
        rows = data.schedules()
        if not rows:
            return
        idx = min(max(0, self.state.sched_sel), len(rows) - 1)
        sched_id = str(rows[idx]["id"])
        repo = str(rows[idx]["repo"]).split("/")[-1]
        from frontier_scout.tui3.overlays import ConfirmScreen

        def _on_confirm() -> None:
            data.schedule_remove(sched_id)
            self.call_later(self._render_pane)

        self.push_screen(
            ConfirmScreen(
                "Remove schedule",
                [f"Remove the scheduled scout for {repo}?"],
                _on_confirm,
                confirm_label="remove",
            )
        )

    # ── Schedule: new (N, FREE) · edit (E, FREE) ──────────────────────────────
    async def action_new_schedule(self) -> None:
        """Open the create-schedule form (N) — FREE local JSON write, no gate.

        Schedule tab only. Pushes the ``ScheduleEditorScreen`` prefilled for a
        NEW schedule (current repo, @daily, file notify, dry-run). Creating one
        never spends and never reaches the network, so there is no cost/network
        gate — the write happens synchronously in ``_on_schedule_create`` once
        the form validates. No-op-safe off-tab.
        """
        if self.state.tab != "schedule":
            return
        from frontier_scout.tui3.overlays import ScheduleEditorScreen

        self.push_screen(
            ScheduleEditorScreen(
                title="New schedule",
                initial={
                    "repo": self.state.repo,
                    "cron_expr": "@daily",
                    "notification": "file",
                    "live": "no",
                },
                on_save=self._on_schedule_create,
            )
        )

    def _on_schedule_create(self, fields: dict[str, Any]) -> None:
        """Persist a new schedule from the form, then re-render + report.

        FREE: ``data.schedule_create`` is a local JSON write (cron already
        normalised + validated by the form). On success re-renders the Schedule
        pane so the new row appears and shows a ResultScreen; on failure surfaces
        the reason. Never raises.
        """
        from frontier_scout.tui3.overlays import ResultScreen

        result = data.schedule_create(
            fields["repo"],
            cron_expr=fields["cron_expr"],
            notification=fields["notification"],
            live=fields["live"],
        )
        if result.get("ok"):
            if self.state.tab == "schedule":
                self.call_later(self._render_pane)
            repo = str(result.get("repo") or "—")
            cron = str(result.get("cron") or fields.get("cron_expr") or "")
            live_note = "live scan" if result.get("live") else "dry-run"
            self.push_screen(ResultScreen(
                "Schedule created",
                [f"[#d9f7ff]{repo}[/]",
                 f"[#6e8aa1]{cron}[/]",
                 (f"[#e3c26f]{live_note}[/]" if result.get("live")
                  else f"[#24d6a8]{live_note}[/]")]))
        else:
            reason = str(result.get("reason") or "Could not create the schedule.")
            self.push_screen(ResultScreen("Schedule", [f"[#ff6b6b]{reason}[/]"]))

    async def action_edit_schedule(self) -> None:
        """Open the edit form for the selected schedule (E) — FREE, no gate.

        Schedule tab only, and only when schedules exist. Resolves the selected
        schedule the same way the toggle/remove/run actions do (``data.schedules``
        + a clamped ``sched_sel``), then pushes the ``ScheduleEditorScreen``
        prefilled from it. The save callback edits the schedule in place — a free
        local JSON write, no spend, no network. No-op-safe off-tab / when empty.
        """
        if self.state.tab != "schedule":
            return
        rows = data.schedules()
        if not rows:
            return
        idx = min(max(0, self.state.sched_sel), len(rows) - 1)
        sched = rows[idx]
        sched_id = str(sched["id"])
        from frontier_scout.tui3.overlays import ScheduleEditorScreen

        self.push_screen(
            ScheduleEditorScreen(
                title="Edit schedule",
                initial={
                    "repo": str(sched["repo"]),
                    "cron_expr": str(sched["cron_expr"]),
                    "notification": str(sched["notification"]),
                    "live": "yes" if sched["live"] else "no",
                },
                on_save=lambda f: self._on_schedule_update(sched_id, f),
            )
        )

    def _on_schedule_update(self, schedule_id: str, fields: dict[str, Any]) -> None:
        """Persist an edit from the form, then re-render + report. FREE; never raises."""
        from frontier_scout.tui3.overlays import ResultScreen

        result = data.schedule_update(
            schedule_id,
            fields["repo"],
            fields["cron_expr"],
            fields["notification"],
            fields["live"],
        )
        if result.get("ok"):
            if self.state.tab == "schedule":
                self.call_later(self._render_pane)
            repo = str(result.get("repo") or "—")
            live_note = "live scan" if fields.get("live") else "dry-run"
            self.push_screen(ResultScreen(
                "Schedule updated",
                [f"[#d9f7ff]{repo}[/]",
                 f"[#6e8aa1]{fields.get('cron_expr') or ''}[/]",
                 (f"[#e3c26f]{live_note}[/]" if fields.get("live")
                  else f"[#24d6a8]{live_note}[/]")]))
        else:
            reason = str(result.get("reason") or "Could not update the schedule.")
            self.push_screen(ResultScreen("Schedule", [f"[#ff6b6b]{reason}[/]"]))

    async def action_open_target(self) -> None:
        """The per-tab "open" action (o). Dispatch by the active tab — FREE.

        Reports → open the last-rendered briefing.html (render first if none
        exists yet). Scout → open the selected verdict's source link in the
        browser. All other tabs are a no-op. Never raises.
        """
        tab = self.state.tab
        if tab == "reports":
            if self._last_report_html and Path(self._last_report_html).exists():
                data.report_open(self._last_report_html)
            else:
                # Nothing rendered yet — render now; on_work_done will open it.
                self._report_worker(open_after=True)
        elif tab == "scout":
            current = self.state.current
            url = getattr(current, "source_url", "") if current else ""
            if url:
                data.report_open(url)
        # Other tabs: intentional no-op.

    def _report_worker(self, *, open_after: bool = False) -> None:
        """Render the latest stored scan on a worker thread (mirrors evaluate).

        ``open_after`` carries the intent to open the result in the browser as
        soon as it lands (used by the Reports "open" action when nothing has
        been rendered yet). FREE — ``data.report_render`` only re-renders stored
        data; no LLM, no network, no spend.
        """
        def _run() -> None:
            try:
                payload = data.report_render(self.state.repo)
                if isinstance(payload, dict):
                    payload = {**payload, "_open_after": open_after}
                self.post_message(WorkDone("report", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("report", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="report")

    # ── Packs: refresh (⏎, FREE/offline) · discover (d, network gate) ─────────
    async def action_discover(self) -> None:
        """The per-tab "discover" action (d). Packs → network refresh behind a gate.

        Refreshing candidates over the MCP registry is a network call (no API
        spend, no LLM — just an HTTP GET), so it is gated behind an explicit
        confirm: nothing reaches the network until the user clears it. All other
        tabs are a no-op. Never raises.
        """
        if self.state.tab != "packs":
            return
        from frontier_scout.tui3.overlays import ConfirmScreen

        def _on_confirm() -> None:
            self._packs_refresh_worker(discover=True)

        self.push_screen(
            ConfirmScreen(
                "Discover packs (network)",
                [
                    "[#e3c26f]Fetches candidates from the MCP registry over the "
                    "network.[/]",
                    "[#6e8aa1]No API spend, no LLM — just an HTTP GET.[/]",
                ],
                _on_confirm,
                confirm_label="discover",
            )
        )

    def _packs_refresh_worker(self, *, discover: bool) -> None:
        """Refresh pack candidates on a worker thread (mirrors ``_report_worker``).

        ``discover=False`` is the offline seed refresh (no network); ``discover=
        True`` is only ever reached AFTER the discover gate's confirm. FREE — no
        API spend, no LLM either way.
        """
        def _run() -> None:
            try:
                payload = data.packs_refresh(discover=discover)
                self.post_message(WorkDone("packs_refresh", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("packs_refresh", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="packs-refresh")

    # ── Guard-railed Scout actions (D = dossier · i = implement & test) ───────
    async def action_dossier(self) -> None:
        """Build an adoption dossier for the selected verdict — FREE, read-only.

        No gate: the dossier never spends and never mutates the working tree.
        It calls ``build_scout_profile`` (~300ms), so it runs on a worker and
        the result lands in a ResultScreen.
        """
        if self.state.tab != "scout" or self.state.current is None:
            return
        verdict = self.state.current

        def _run() -> None:
            try:
                payload = data.dossier(verdict, self.state.repo)
                self.post_message(WorkDone("dossier", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("dossier", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="dossier")

    async def action_implement(self) -> None:
        """Implement & test the selected verdict — behind a COST gate.

        Demo mode runs the backend with ``dry_run=True`` (zero spend, no
        mutation — the synthetic path short-circuits before any provider or
        file write). Live mode spends only AFTER the explicit gate confirm.
        """
        if self.state.tab != "scout" or self.state.current is None:
            return
        from frontier_scout.tui3.overlays import ConfirmScreen

        verdict = self.state.current
        tool = verdict.tool_name
        demo = self.state.demo
        if demo:
            lines = [
                f"[#a9bccd]Stage a minimal, tested adoption of {tool} in an "
                "isolated worktree.[/]",
                "[#24d6a8]Demo mode: dry-run, no API spend.[/]",
            ]
        else:
            lines = [
                f"[#a9bccd]Stage a minimal, tested adoption of {tool} in an "
                "isolated worktree.[/]",
                f"[#e3c26f]This calls {self.state.provider} and may cost "
                "~$0.30+. Files are written in an isolated worktree and only "
                "kept if tests pass.[/]",
            ]

        def _on_confirm() -> None:
            self._implement_worker(verdict, dry_run=demo)

        self.push_screen(
            ConfirmScreen(f"Implement & test {tool}", lines, _on_confirm)
        )

    def _implement_worker(self, verdict: Any, *, dry_run: bool) -> None:
        def _run() -> None:
            try:
                payload = data.implement(verdict, self.state.repo, dry_run=dry_run)
                self.post_message(WorkDone("implement", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("implement", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="implement")

    # ── Guard-railed actions: evaluate / lab (Scout) ──────────────────────────
    async def action_evaluate(self) -> None:
        """Full (judged) evaluation of the selected verdict — behind a COST gate.

        ``evaluate_url`` resolves a provider judge and SPENDS real money with no
        dry-run. The worker is kicked only AFTER the explicit gate confirm.
        """
        if self.state.tab != "scout" or self.state.current is None:
            return
        verdict = self.state.current
        if not verdict.source_url:
            return
        from frontier_scout.tui3.overlays import ConfirmScreen

        lines = [
            f"[#e3c26f]Calls {self.state.provider} (judge) — costs money. "
            "No dry-run.[/]"
        ]

        def _on_confirm() -> None:
            self._evaluate_worker(verdict)

        self.push_screen(
            ConfirmScreen(f"Evaluate {verdict.tool_name}", lines, _on_confirm,
                          confirm_label="evaluate")
        )

    def _evaluate_worker(self, verdict: Any) -> None:
        def _run() -> None:
            try:
                payload = data.evaluate(verdict, self.state.repo)
                self.post_message(WorkDone("evaluate", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("evaluate", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="evaluate")

    async def action_lab(self) -> None:
        """Sandbox trial of the selected verdict's tool — behind a gate.

        Free of API spend, but installs the package from PyPI into a temp
        sandbox and runs a probe. The worker is kicked only AFTER the confirm.
        """
        if self.state.tab != "scout" or self.state.current is None:
            return
        verdict = self.state.current
        from frontier_scout.tui3.overlays import ConfirmScreen

        lines = [
            f"[#e3c26f]Installs {verdict.tool_name} into a temp sandbox "
            "(PyPI download) and runs a probe. No API spend.[/]"
        ]

        def _on_confirm() -> None:
            self._lab_worker(verdict)

        self.push_screen(
            ConfirmScreen(f"Lab {verdict.tool_name}", lines, _on_confirm,
                          confirm_label="lab")
        )

    def _lab_worker(self, verdict: Any) -> None:
        def _run() -> None:
            try:
                payload = data.lab(verdict, self.state.repo)
                self.post_message(WorkDone("lab", payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("lab", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="lab")

    # ── Guard-railed actions: clear history / reconfigure (Settings) ──────────
    async def action_clear_history(self) -> None:
        """Permanently delete saved scans for this repo — typed-confirm gate."""
        if self.state.tab != "settings":
            return
        from frontier_scout.tui3.overlays import TypedConfirmScreen

        def _on_confirm() -> None:
            self._clear_history_worker()

        self.push_screen(
            TypedConfirmScreen(
                "Clear scan history",
                ["[#ff6b6b]Permanently deletes saved scans for this repo.[/]"],
                token="clear",
                on_confirm=_on_confirm,
            )
        )

    def _clear_history_worker(self) -> None:
        def _run() -> None:
            try:
                deleted = data.clear_history(self.state.repo)
                self.post_message(WorkDone("clear", deleted))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("clear", str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group="clear")

    async def action_reconfigure(self) -> None:
        """Relaunch the setup wizard (Mission Control exits with code 42)."""
        if self.state.tab != "settings":
            return
        from frontier_scout.tui3.overlays import ConfirmScreen

        self.push_screen(
            ConfirmScreen(
                "Reconfigure",
                ["Relaunch the setup wizard. Mission Control will exit and reopen."],
                lambda: self.exit(42),
                confirm_label="relaunch",
            )
        )

    async def action_toggle_unicode(self) -> None:
        self.state = self.state.with_(unicode=not self.state.unicode)
        await self._render()
        # Toast so the keypress visibly "lands" (no behaviour change).
        try:
            self.notify("unicode glyphs" if self.state.unicode else "ascii glyphs")
        except Exception:  # noqa: BLE001 — toast is best-effort feedback only
            self._set("#mc-compass", self._compass_text())

    async def action_toggle_color(self) -> None:
        self.state = self.state.with_(color=not self.state.color)
        self.screen.set_class(not self.state.color, "-mono")
        await self._render()
        # Toast so the keypress visibly "lands" (no behaviour change).
        try:
            self.notify("color" if self.state.color else "mono")
        except Exception:  # noqa: BLE001 — toast is best-effort feedback only
            self._set("#mc-compass", self._compass_text())

    def action_help(self) -> None:
        from frontier_scout.tui3.overlays import HelpScreen

        self.push_screen(HelpScreen())

    def action_notifications(self) -> None:
        from frontier_scout.tui3.overlays import NotificationsScreen

        self.push_screen(NotificationsScreen())

    def action_palette(self) -> None:
        from frontier_scout.tui3.overlays import CommandPalette

        self.push_screen(CommandPalette())

    def action_switch_repo(self) -> None:
        from frontier_scout.tui3.overlays import RepoSwitcherScreen

        repos = data.list_repos(self.state.repo)
        self.push_screen(RepoSwitcherScreen(repos, self.state.repo))

    def switch_repo(self, path: str) -> None:
        """Re-init state for ``path`` (preserving UI prefs), then re-scout (§9).

        Verdicts/funnel/languages/profile all become relative to the new repo —
        an honest switch, never a label-only change.
        """
        fresh = data.initial_state(Path(path), demo=self.state.demo)
        self.state = fresh.with_(
            tab=self.state.tab, scope="all", sel=0,
            color=self.state.color, unicode=self.state.unicode,
        )
        self._refresh_nav()
        self.call_later(self._render)
        self.run_scout(dry_run=self.state.demo)
        try:
            self.notify(f"pointed at {self.state.repo_name} · re-scouting")
        except Exception:  # noqa: BLE001 — toast is best-effort feedback only
            pass

    def run_palette_action(self, aid: str) -> None:
        kind, _, val = aid.partition(":")
        if kind == "tab":
            self.call_later(self._goto, val)
        # ── capability commands: go to the owning tab, THEN run the action ────
        # Each chains _goto (async) before reusing the existing method, so the
        # right tab is showing when the result lands. All reuse existing logic
        # and are safe if state is incomplete (the workers/actions self-guard).
        elif aid == "report:render":
            self.call_later(self._goto_then, "reports", self._report_worker)
        elif aid == "report:open":
            self.call_later(self._goto_then_async, "reports", self.action_open_target)
        elif aid == "packs:refresh":
            self.call_later(
                self._goto_then, "packs", lambda: self._packs_refresh_worker(discover=False)
            )
        elif aid == "schedule:new":
            self.call_later(self._goto_then_async, "schedule", self.action_new_schedule)
        elif val == "scout":
            self.call_later(self.action_scout_now)
        elif val == "refresh":
            self.call_later(self.action_refresh)
        elif val == "dossier":
            self.call_later(self.action_dossier)
        elif val == "implement":
            self.call_later(self.action_implement)
        elif val == "evaluate":
            self.call_later(self.action_evaluate)
        elif val == "lab":
            self.call_later(self.action_lab)
        elif val == "switch_repo":
            self.call_later(self.action_switch_repo)
        elif val == "clear":
            self.call_later(self.action_clear_history)
        elif val == "reconfigure":
            self.call_later(self.action_reconfigure)
        elif val == "unicode":
            self.call_later(self.action_toggle_unicode)
        elif val == "color":
            self.call_later(self.action_toggle_color)
        elif val == "help":
            self.action_help()
        elif val == "notifications":
            self.action_notifications()

    async def _goto_then(self, tab: str, fn) -> None:
        """Switch to ``tab`` (async) then run a SYNC callable. Never raises."""
        await self._goto(tab)
        try:
            fn()
        except Exception:  # noqa: BLE001 — reused methods already self-guard
            pass

    async def _goto_then_async(self, tab: str, coro_fn) -> None:
        """Switch to ``tab`` (async) then await an ASYNC callable. Never raises."""
        await self._goto(tab)
        try:
            await coro_fn()
        except Exception:  # noqa: BLE001 — reused methods already self-guard
            pass

    async def action_scout_now(self) -> None:
        await self._goto("scout")
        self.run_scout(dry_run=self.state.demo)

    async def action_refresh(self) -> None:
        """Refresh the active capability tab via a worker (off the render path)."""
        tab = self.state.tab
        if tab == "scout":
            self.run_scout(dry_run=self.state.demo)
            return
        if tab in ("guard", "deps", "settings"):
            self._refresh_worker(tab)

    def _refresh_worker(self, kind: str) -> None:
        def _run() -> None:
            try:
                if kind == "guard":
                    payload = data.guard(self.state.repo, strict=False)
                elif kind == "deps":
                    payload = data.dependencies(self.state.repo)
                else:  # settings
                    payload = {
                        "policy": data.policy(self.state.repo),
                        "profile": data.repo_profile(self.state.repo),
                        "doctor": data.doctor(),
                    }
                self.post_message(WorkDone(kind, payload))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed(kind, str(exc)))

        self.run_worker(_run, thread=True, exclusive=False, group=f"cap-{kind}")

    # ── worker bridge ────────────────────────────────────────────────────────
    def run_scout(self, *, dry_run: bool) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._refresh_chrome()
        self._scout_worker(dry_run)

    def _scout_worker(self, dry_run: bool) -> None:
        # NOTE: call run_worker() directly rather than the @work decorator.
        # @work assumes the wrapped callable is a method (self = args[0]); on a
        # zero-arg nested function it raises IndexError. run_worker(thread=True)
        # has the same off-thread semantics without that assumption.
        def _run() -> None:
            reporter = TuiReporter(self, "scout")
            try:
                result = data.run_scan(
                    self.state.repo, dry_run=dry_run, scope=self.state.scope, reporter=reporter)
                self.post_message(WorkDone("scout", result))
            except Exception as exc:  # noqa: BLE001
                self.post_message(WorkFailed("scout", str(exc)))

        self.run_worker(_run, thread=True, exclusive=True, group="scout")

    def on_progress(self, message: Progress) -> None:
        self._set("#mc-compass", f"[#24d6a8]scanning…[/] [#6e8aa1]{message.text}[/]")

    async def on_work_done(self, message: WorkDone) -> None:
        self._scanning = False
        if message.kind == "scout":
            r = message.payload
            self.state = self.state.with_(
                verdicts=r["verdicts"], funnel=r["funnel"],
                languages=r["languages"] or self.state.languages, sel=0)
            self._refresh_nav()
            if self.state.tab == "scout":
                await self._render_pane()
        elif message.kind == "guard":
            self.state = self.state.with_(guard_cache=message.payload)
            if self.state.tab == "guard":
                await self._render_pane()
        elif message.kind == "deps":
            self.state = self.state.with_(deps_cache=message.payload)
            if self.state.tab == "deps":
                await self._render_pane()
        elif message.kind == "settings":
            self.state = self.state.with_(settings_cache=message.payload)
            if self.state.tab == "settings":
                await self._render_pane()
        elif message.kind == "dossier":
            from frontier_scout.tui3.overlays import ResultScreen

            title, lines = _dossier_result_lines(message.payload)
            self.push_screen(ResultScreen(title, lines))
        elif message.kind == "implement":
            from frontier_scout.tui3.overlays import ResultScreen

            title, lines = _implement_result_lines(message.payload)
            self.push_screen(ResultScreen(title, lines))
        elif message.kind == "evaluate":
            from frontier_scout.tui3.overlays import ResultScreen

            title, lines = _evaluate_result_lines(message.payload)
            self.push_screen(ResultScreen(title, lines))
        elif message.kind == "lab":
            from frontier_scout.tui3.overlays import ResultScreen

            title, lines = _lab_result_lines(message.payload)
            self.push_screen(ResultScreen(title, lines))
        elif message.kind == "report":
            from frontier_scout.tui3.overlays import ResultScreen

            p = message.payload or {}
            if p.get("ok"):
                self._last_report_html = p.get("html") or None
                # Honour a deferred open request (Reports "open" with nothing
                # rendered yet) before showing the result screen.
                if p.get("_open_after") and self._last_report_html:
                    data.report_open(self._last_report_html)
                title, lines = _report_result_lines(p)
                self.push_screen(ResultScreen(title, lines))
            else:
                reason = str(p.get("reason") or "Could not render the report.")
                self.push_screen(ResultScreen("Report", [f"[#ff6b6b]{reason}[/]"]))
        elif message.kind == "packs_refresh":
            from frontier_scout.tui3.overlays import ResultScreen

            p = message.payload or {}
            if p.get("ok"):
                title, lines = _packs_refresh_result_lines(p)
                self.push_screen(ResultScreen(title, lines))
                # The packs pane is rebuilt from the store on every render, so a
                # re-render surfaces the freshly written candidates.
                if self.state.tab == "packs":
                    await self._render_pane()
            else:
                reason = str(p.get("reason") or "Could not refresh packs.")
                self.push_screen(ResultScreen("Packs", [f"[#ff6b6b]{reason}[/]"]))
        elif message.kind == "schedule_run":
            from frontier_scout.tui3.overlays import ResultScreen

            p = message.payload or {}
            if p.get("ok"):
                dry = bool(p.get("dry_run"))
                repo = str(p.get("repo") or "—")
                verdicts = int(p.get("verdicts") or 0)
                cost = float(p.get("cost") or 0.0)
                note = (
                    "[#24d6a8]Dry-run — seeded sample, no spend, no network.[/]"
                    if dry else
                    "[#e3c26f]Live scout — judged against the provider.[/]"
                )
                title = "Scheduled scout" + (" (dry-run)" if dry else "")
                self.push_screen(ResultScreen(
                    title,
                    [f"[#d9f7ff]{repo}[/]",
                     f"[#6e8aa1]{verdicts} verdicts[/]",
                     f"[#6e8aa1]${cost:.2f}[/]",
                     note]))
            else:
                reason = str(p.get("reason") or "Could not run the schedule.")
                self.push_screen(ResultScreen("Schedule run", [f"[#ff6b6b]{reason}[/]"]))
            # last_run may have changed — re-render so the pane reflects it.
            if self.state.tab == "schedule":
                await self._render_pane()
        elif message.kind == "clear":
            from frontier_scout.tui3.overlays import ResultScreen

            n = int(message.payload or 0)
            self.push_screen(ResultScreen("Clear history", [f"Cleared {n} scan(s)."]))
            self._refresh_nav()
            if self.state.tab == "scout":
                await self._render_pane()
        self._refresh_chrome()

    def on_work_failed(self, message: WorkFailed) -> None:
        self._scanning = False
        self._set("#mc-compass", f"[#ff6b6b]{message.kind} failed: {message.error}[/]")


def _dossier_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a projected dossier dict into ResultScreen title + markup lines."""
    p = payload or {}
    tool = p.get("tool_name") or "tool"
    title = f"Dossier · {tool}"
    if not p:
        return title, ["[#ff6b6b]Could not build a dossier for this item.[/]"]
    lines: list[str] = []
    verdict = str(p.get("verdict") or "").upper()
    if verdict:
        lines.append(f"[#6e8aa1]verdict[/] [#d9f7ff b]{verdict}[/]")
    lines.append(
        f"[#6e8aa1]fit[/] {p.get('fit') or '−'}   "
        f"[#6e8aa1]risk[/] {p.get('risk') or '−'}   "
        f"[#6e8aa1]source trust[/] {p.get('source_trust') or '−'}"
    )
    if p.get("policy"):
        lines.append(f"[#6e8aa1]policy[/] [#a9bccd]{p['policy']}[/]")
    if p.get("why"):
        lines.append("")
        lines.append(f"[#a9bccd]{p['why']}[/]")
    if p.get("fit_reasons"):
        lines.append("")
        lines.append("[#6e8aa1]why it fits[/]")
        for r in p["fit_reasons"]:
            lines.append(f"  [#24d6a8]·[/] [#a9bccd]{r}[/]")
    if p.get("gaps"):
        lines.append("")
        lines.append("[#6e8aa1]unknowns / gaps[/]")
        for gap in p["gaps"]:
            lines.append(f"  [#e3c26f]·[/] [#a9bccd]{gap}[/]")
    if p.get("next_step"):
        lines.append("")
        lines.append(f"[#6e8aa1]next safe step[/]  [#a9bccd]{p['next_step']}[/]")
    if p.get("receipt_path"):
        lines.append("")
        lines.append(f"[#6e8aa1]saved[/] [#7aa6ff]{p['receipt_path']}[/]")
    return title, lines


def _implement_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a projected implement dict into ResultScreen title + markup lines."""
    p = payload or {}
    status = str(p.get("status") or "error")
    color = {"passed": "#24d6a8", "dry_run": "#7aa6ff", "prepared": "#7aa6ff",
             "failed": "#e3c26f", "error": "#ff6b6b"}.get(status, "#a9bccd")
    title = "Implement & test"
    lines: list[str] = [f"[#6e8aa1]status[/] [{color} b]{status.upper()}[/]"]
    if p.get("summary"):
        lines.append(f"[#a9bccd]{p['summary']}[/]")
    if p.get("what_you_get"):
        lines.append("")
        lines.append(f"[#6e8aa1]what you get[/] [#a9bccd]{p['what_you_get']}[/]")
    if p.get("error"):
        lines.append("")
        lines.append(f"[#ff6b6b]{p['error']}[/]")
    files = p.get("files") or []
    if files:
        lines.append("")
        lines.append(f"[#6e8aa1]files ({len(files)})[/]")
        for f in files[:20]:
            lines.append(f"  [#7aa6ff]{f}[/]")
    diff = str(p.get("diff") or "")
    if diff:
        lines.append("")
        lines.append("[#6e8aa1]diff[/]")
        for ln in diff.splitlines()[:60]:
            lines.append(f"[#6e8aa1]{_escape_markup(ln)}[/]")
    out = str(p.get("test_output") or "")
    if out:
        lines.append("")
        lines.append("[#6e8aa1]test output[/]")
        for ln in out.splitlines()[:40]:
            lines.append(f"[#6e8aa1]{_escape_markup(ln)}[/]")
    return title, lines


def _evaluate_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a projected evaluation dict into ResultScreen title + markup lines."""
    p = payload or {}
    tool = p.get("tool_name") or "tool"
    title = f"Evaluation · {tool}"
    if not p.get("ok"):
        err = p.get("error")
        lines = ["[#ff6b6b]Evaluation failed.[/]"]
        if err:
            lines.append(f"[#6e8aa1]{_escape_markup(str(err))}[/]")
        return title, lines
    lines: list[str] = [
        f"[#6e8aa1]fit[/] {p.get('fit') or '−'}   "
        f"[#6e8aa1]risk[/] {p.get('risk') or '−'}   "
        f"[#6e8aa1]source trust[/] {p.get('source_trust') or '−'}"
    ]
    if p.get("category"):
        lines.append(f"[#6e8aa1]category[/] [#a9bccd]{p['category']}[/]")
    if p.get("summary"):
        lines.append("")
        lines.append(f"[#a9bccd]{p['summary']}[/]")
    evidence = p.get("evidence") or []
    if evidence:
        lines.append("")
        lines.append("[#6e8aa1]evidence[/]")
        for e in evidence[:10]:
            lines.append(f"  [#24d6a8]·[/] [#a9bccd]{_escape_markup(str(e))}[/]")
    return title, lines


def _lab_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a projected lab/trial dict into ResultScreen title + markup lines."""
    p = payload or {}
    tool = p.get("tool_name") or "tool"
    title = f"Lab · {tool}"
    if not p.get("ok"):
        err = p.get("error")
        lines = ["[#ff6b6b]Trial failed.[/]"]
        if err:
            lines.append(f"[#6e8aa1]{_escape_markup(str(err))}[/]")
        return title, lines
    status = str(p.get("status") or "")
    color = {"passed": "#24d6a8", "skipped": "#7aa6ff", "failed": "#e3c26f",
             "error": "#ff6b6b"}.get(status, "#a9bccd")
    lines: list[str] = [f"[#6e8aa1]status[/] [{color} b]{status.upper() or '−'}[/]"]
    if p.get("runtime"):
        lines.append(f"[#6e8aa1]runtime[/] [#a9bccd]{p['runtime']}[/]")
    if p.get("detail"):
        lines.append("")
        lines.append(f"[#a9bccd]{p['detail']}[/]")
    return title, lines


def _report_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a rendered-report dict into ResultScreen title + markup lines."""
    p = payload or {}
    title = "Report rendered"
    out_dir = str(p.get("dir") or "")
    files = p.get("files") or []
    lines: list[str] = []
    if out_dir:
        lines.append(f"[#6e8aa1]written to[/] [#7aa6ff]{_escape_markup(out_dir)}[/]")
    if files:
        lines.append("")
        lines.append(f"[#6e8aa1]files ({len(files)})[/]")
        for fn in files[:20]:
            lines.append(f"  [#a9bccd]{_escape_markup(str(fn))}[/]")
    lines.append("")
    lines.append("[#24d6a8]Press o to open the report in your browser.[/]")
    return title, lines


def _packs_refresh_result_lines(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Format a packs-refresh dict into ResultScreen title + markup lines."""
    p = payload or {}
    discover = bool(p.get("discover"))
    title = "Packs refreshed" + (" · discover" if discover else "")
    total = int(p.get("total") or 0)
    rows = p.get("packs") or []
    lines: list[str] = [
        f"[#6e8aa1]candidates written[/] [#d9f7ff b]{total}[/] "
        f"[#6e8aa1]across {len(rows)} pack(s)[/]"
    ]
    if rows:
        lines.append("")
        for r in rows[:20]:
            name = _escape_markup(str((r or {}).get("name") or "pack"))
            count = int((r or {}).get("count") or 0)
            lines.append(f"  [#a9bccd]{name}[/] [#6e8aa1]·[/] [#7aa6ff]{count}[/]")
    lines.append("")
    if discover:
        lines.append(
            "[#6e8aa1]Fetched over the network from the MCP registry — "
            "no API spend, no LLM.[/]"
        )
    else:
        lines.append(
            "[#24d6a8]Offline refresh — seed candidates only, no network. "
            "Press d to discover over the network.[/]"
        )
    return title, lines


def _escape_markup(text: str) -> str:
    """Neutralise Rich markup brackets so diff/test text renders literally."""
    return text.replace("[", "\\[")


def _vis_len(markup: str) -> int:
    """Approx visible length of Rich console markup (strips [..] tags)."""
    out, depth = 0, 0
    for ch in markup:
        if ch == "[":
            depth += 1
        elif ch == "]":
            if depth:
                depth -= 1
        elif depth == 0:
            out += 1
    return out
