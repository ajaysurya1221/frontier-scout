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
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from frontier_scout.tui3 import data
from frontier_scout.tui3.kit import MIN_COLS, MIN_ROWS, breakpoint_for, glyphs, mono
from frontier_scout.tui3.messages import Progress, TuiReporter, WorkDone, WorkFailed
from frontier_scout.tui3.state import AppState

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
        *[Binding(str(i + 1), f"goto_{t}", t, show=False) for i, (t, _, _) in enumerate(TABS)],
        Binding("j,down", "move(1)", "down", show=False),
        Binding("k,up", "move(-1)", "up", show=False),
        Binding("right", "scope(1)", "scope", show=False),
        Binding("left", "scope(-1)", "scope", show=False),
        Binding("a", "ask", "ask", show=False),
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

    # ── lifecycle ────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Static(id="mc-header")
        with Container(id="mc-body"):
            yield Static(id="mc-rail")
            yield Static(id="mc-tabstrip")
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
        return max(1, sz.width), max(1, sz.height)

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
            rail = self.query_one("#mc-rail", Static)
            strip = self.query_one("#mc-tabstrip", Static)
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

        if bp.rail:
            rail.set_class(bp.rail_compact, "compact")
            rail.update(self._paint(self._rail_text(compact=bp.rail_compact)))
        else:
            strip.update(self._paint(self._tabstrip_text(numeric=bp.numeric_tabs)))

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
        """Update rail/tabstrip markup in place (e.g. after a tab change)."""
        bp = breakpoint_for(*self._term_size)
        if bp.rail:
            self._set("#mc-rail", self._rail_text(compact=bp.rail_compact))
        else:
            self._set("#mc-tabstrip", self._tabstrip_text(numeric=bp.numeric_tabs))

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
            left += "[#d9f7ff b]frontier scout[/] [#25405c]" + g["pip"] + "[/] "
        left += f"[#a9bccd]{self.state.repo_name}[/]"
        if not micro:
            left += f"  [#6e8aa1]{g['dot']} {self.state.provider}[/]"
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
            hints = [("1-8", "tabs"), ("j/k", "move"), ("s", "scout"), ("g", "guard"),
                     ("u", "ascii"), ("c", "mono"), ("?", "help"), ("q", "quit")]
        parts = " ".join(f"[#24d6a8 b]{k}[/][#6e8aa1] {label}[/]" for k, label in hints)
        if self._scanning:
            tail = "[#24d6a8]scanning…[/]"
        else:
            tail = f"[#6e8aa1]{len(self.state.verdicts)} verdicts {g['pip']} ${self.state.funnel.cost:.2f}[/]"
        cols, _ = self._term_size
        pad = max(1, cols - _vis_len(parts) - _vis_len(tail) - 2)
        return parts + " " * pad + tail

    def _rail_text(self, *, compact: bool) -> str:
        g = glyphs(self.state.unicode)
        lines = [g["radar_core"] if compact else f"{g['radar_core']} [#d9f7ff b]scout[/]", ""]
        for i, (tid, label, _short) in enumerate(TABS):
            on = tid == self.state.tab
            badge = self._badge(tid)
            if compact:
                cell = f"{i + 1}"
            else:
                btxt = f"  {badge}" if badge else ""
                cell = f"{i + 1} {label}{btxt}"
            if on:
                lines.append(f"[#d9f7ff b on #10202a]{cell}[/]")
            else:
                lines.append(f"[#6e8aa1]{cell}[/]")
        return "\n".join(lines)

    def _tabstrip_text(self, *, numeric: bool) -> str:
        cells = []
        for i, (tid, _label, short) in enumerate(TABS):
            on = tid == self.state.tab
            cell = f"{i + 1}" if numeric else f"{i + 1}{short}"
            cells.append(f"[#24d6a8 b]{cell}[/]" if on else f"[#6e8aa1]{cell}[/]")
        return "  ".join(cells)

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

    async def action_move(self, delta: int) -> None:
        if self.state.tab == "scout" and self.state.verdicts:
            self.state = self.state.move(delta)
            self._refresh_nav()
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

    async def action_toggle_unicode(self) -> None:
        self.state = self.state.with_(unicode=not self.state.unicode)
        await self._render()

    async def action_toggle_color(self) -> None:
        self.state = self.state.with_(color=not self.state.color)
        self.screen.set_class(not self.state.color, "-mono")
        await self._render()

    def action_help(self) -> None:
        from frontier_scout.tui3.overlays import HelpScreen

        self.push_screen(HelpScreen())

    def action_notifications(self) -> None:
        from frontier_scout.tui3.overlays import NotificationsScreen

        self.push_screen(NotificationsScreen())

    def action_palette(self) -> None:
        from frontier_scout.tui3.overlays import CommandPalette

        self.push_screen(CommandPalette())

    def run_palette_action(self, aid: str) -> None:
        kind, _, val = aid.partition(":")
        if kind == "tab":
            self.call_later(self._goto, val)
        elif val == "scout":
            self.call_later(self.action_scout_now)
        elif val == "refresh":
            self.call_later(self.action_refresh)
        elif val == "unicode":
            self.call_later(self.action_toggle_unicode)
        elif val == "color":
            self.call_later(self.action_toggle_color)
        elif val == "help":
            self.action_help()
        elif val == "notifications":
            self.action_notifications()

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
        self._refresh_chrome()

    def on_work_failed(self, message: WorkFailed) -> None:
        self._scanning = False
        self._set("#mc-compass", f"[#ff6b6b]scan failed: {message.error}[/]")


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
