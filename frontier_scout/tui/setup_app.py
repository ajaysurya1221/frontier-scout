"""Mission Control v1.2 — the honest fix.

No splash, no welcome modal, no demo features in the TUI. Two tabs:
Scout (the entire product) and Settings. Brand bar gains a clickable
'open report' link.
"""

from __future__ import annotations

import webbrowser
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import RichLog, Static, TabbedContent, TabPane

from frontier_scout import __version__
from frontier_scout.notifications import unread_count
from frontier_scout.tui.diff_modal import DiffScreen
from frontier_scout.tui.modals import HelpScreen, QuitConfirmScreen, RepoPathPromptScreen
from frontier_scout.tui.notifications_modal import NotificationsScreen
from frontier_scout.tui.setup_diagnostics import SetupDiagnostics, setup_diagnostics
from frontier_scout.tui.tabs import DEFAULT_TAB, TAB_REGISTRY, TAB_SLUGS
from frontier_scout.tui.tabs.scout_tab import ScoutTab
from frontier_scout.tui.tabs.settings_tab import SettingsTab


class SetupApp(App[None]):
    """Two-tab Mission Control: Scout + Settings."""

    CSS = """
    Screen {
        background: #0b1117;
        color: #d9f7ff;
    }

    #brand-bar {
        height: 1;
        padding: 0 1;
        background: #0d1622;
        color: #d9f7ff;
    }

    #status-banner {
        height: 1;
        padding: 0 2;
        background: #0d1622;
        color: #24d6a8;
    }

    #status-banner.warn { color: #e3c26f; }
    #status-banner.info { color: #7aa6ff; }
    #status-banner.error { color: #ff6b6b; }

    #analyse-bar {
        height: 2;
        padding: 0 2;
        background: #0d1622;
        color: #d9f7ff;
    }

    TabbedContent {
        height: 1fr;
    }

    TabbedContent TabPane {
        padding: 1 1 0 1;
    }

    Tabs { background: #0d1622; }
    Tab { color: #6e8aa1; }
    Tab.-active { color: #24d6a8; text-style: bold; }

    #result-log {
        height: 6;
        border: round #25405c;
        background: #0d1622;
        color: #d9f7ff;
    }

    #result-log:focus-within { border: round #24d6a8; }

    /* v1.3.0 Stream B — per-tab subtitle. */
    #tab-subtitle {
        height: 1;
        padding: 0 2;
        background: #0d1622;
        color: #d9f7ff;
    }
    """

    BINDINGS: ClassVar = [
        Binding("q", "request_quit", "Quit"),
        # v1.3.0 Stream B — ? opens the glossary (term reference); the
        # keymap reference moves to H (still discoverable from the
        # glossary footer). Old muscle memory hitting ? gets help with
        # vocabulary first, which is what newcomers actually need.
        Binding("question_mark", "show_glossary", "Glossary", show=True),
        Binding("?", "show_glossary", "Glossary"),
        Binding("H", "show_help", "Help", show=False),
        Binding("slash", "edit_repo", "Repo path"),
        Binding("/", "edit_repo", "Repo path"),
        Binding("ctrl+l", "clear_log", "Clear log", show=False),
        Binding("ctrl+n", "open_notifications", "Notifications", show=False),
        Binding("d", "open_diff", "Diff vs last scan", show=False),
        Binding("r", "open_report", "Open report", show=False),
        Binding("1", "jump_tab(0)", "Scout", show=False),
        Binding("2", "jump_tab(1)", "Settings", show=False),
    ]

    def __init__(
        self,
        diagnostics: SetupDiagnostics,
        *,
        show_splash: bool = True,  # accepted but ignored — splash deleted in v1.2.
        initial_tab: str = DEFAULT_TAB,
        universal_mode: bool = False,
    ) -> None:
        super().__init__()
        self.diagnostics = diagnostics
        self._initial_tab = initial_tab if initial_tab in TAB_SLUGS else DEFAULT_TAB
        # Stream J — when set, ScoutTab skips repo-profile-based filtering
        # and surfaces every seeded verdict so the user gets value even
        # without a repo. Toggled either from the constructor (rare) or
        # from the picker callback in ``runner.py`` (typical).
        self.universal_mode = universal_mode

    # ------------------------------------------------------------------
    # Compose / mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        from frontier_scout.tui.glossary import TAB_SUBTITLES
        from frontier_scout.tui.progress_view import ProgressStrip, StatusStrip

        yield Static(self._brand_bar_text(), id="brand-bar", markup=True)
        yield Static(
            "Local-first. No repo content sent to an LLM. No tools installed.",
            id="status-banner",
        )
        yield Static(self._analyse_bar_text(), id="analyse-bar", markup=True)
        # v1.3.0 Stream B — per-tab subtitle, refreshed in on_tab_changed.
        yield Static(
            self._tab_subtitle(self._initial_tab, TAB_SUBTITLES),
            id="tab-subtitle",
            markup=True,
        )
        with TabbedContent(initial=self._initial_tab):
            for spec in TAB_REGISTRY:
                with TabPane(spec.title, id=spec.slug):
                    yield self._build_tab(spec.slug)
        # v1.3.0 Stream B — sticky status row + progress bar.
        yield StatusStrip()
        yield ProgressStrip()
        yield RichLog(id="result-log", markup=True, auto_scroll=True, wrap=True)

    def _tab_subtitle(self, slug: str, subtitles) -> str:
        return subtitles.get(slug, "")

    def _build_tab(self, slug: str) -> Container:
        mapping = {"scout": ScoutTab, "settings": SettingsTab}
        return mapping[slug](self)

    def on_mount(self) -> None:
        self._set_status_banner(
            "Local-first. No repo content sent to an LLM. No tools installed.",
            tone="ok",
        )
        # Stream L — only warn at the *true* POSIX minimum (80x24).
        # Below that the layout genuinely can't fit; above that we
        # adapt via the .compact CSS class in on_resize.
        if self.size.width < 80 or self.size.height < 24:
            self._set_status_banner(
                "Terminal is below 80×24 — resize, or run: frontier-scout setup --plain",
                tone="warn",
            )
        self._apply_compact_layout()
        self.log_event(f"Ready · repo {self.diagnostics.repo}", tone="muted")
        self._remember_recent_repo(self.diagnostics.repo)

    def on_resize(self, event) -> None:  # type: ignore[no-untyped-def]
        # Stream L — toggle the .compact class on the ScoutTab so the
        # layout reflows live when the user resizes their terminal
        # (or attaches a smaller pane in tmux/VS Code).
        self._apply_compact_layout()
        # Brand bar is also adaptive — re-render it.
        try:
            self.query_one("#brand-bar", Static).update(self._brand_bar_text())
        except Exception:  # noqa: BLE001 — pre-mount resize event
            pass

    def _apply_compact_layout(self) -> None:
        try:
            from frontier_scout.tui.tabs.scout_tab import ScoutTab

            scout = self.query_one(ScoutTab)
        except Exception:  # noqa: BLE001 — tab not mounted yet
            return
        narrow = self.size.width < 100 or self.size.height < 28
        if narrow:
            scout.add_class("compact")
        else:
            scout.remove_class("compact")

    def _remember_recent_repo(self, repo: str) -> None:
        from frontier_scout.store import read_setup_state, write_setup_state

        state = read_setup_state()
        recent = [r for r in (state.get("recent_repos") or []) if r != repo]
        recent.insert(0, repo)
        state["recent_repos"] = recent[:10]
        write_setup_state(state)

    # ------------------------------------------------------------------
    # Bars
    # ------------------------------------------------------------------

    def _brand_bar_text(self) -> str:
        unread = unread_count()
        chip = (
            f"   [#e3c26f bold]({unread} new)[/]"
            if unread > 0
            else ""
        )
        # Stream J — when universal mode is active, show that prominently
        # so the user always knows verdicts aren't tailored.
        if self.universal_mode:
            repo_chip = "[#e3c26f]🌐 universal mode (not tailored)[/]"
        else:
            repo_chip = f"[#7aa6ff]📁 {self.diagnostics.repo}[/]"
        # Stream L — when the terminal is narrow, drop the tagline and
        # shorten the repo chip to its basename to keep the brand bar
        # on one line.
        narrow = bool(self.size.width and self.size.width < 100)
        if narrow and not self.universal_mode:
            repo_basename = Path(self.diagnostics.repo).name or self.diagnostics.repo
            repo_chip = f"[#7aa6ff]📁 {repo_basename}[/]"
        if narrow:
            return (
                f"[#24d6a8 bold]◉ FRONTIER · SCOUT[/]  "
                f"[#6e8aa1]v{__version__}[/]   "
                f"{repo_chip}   "
                f"[#24d6a8 underline]📊 r[/]{chip}"
            )
        return (
            f"[#24d6a8 bold]◉ FRONTIER · SCOUT[/]  "
            f"[#6e8aa1]v{__version__}[/]   "
            f"[#6e8aa1]the radar for latest AI releases that fit your repo[/]   "
            f"{repo_chip}   "
            f"[#24d6a8 underline]📊 report (press r)[/]{chip}"
        )

    def _analyse_bar_text(self) -> str:
        p = self.diagnostics.profile
        evidence = p.import_evidence
        imports_summary = ""
        if evidence.available and evidence.top_python:
            top = " ".join(f"{name}×{count}" for name, count in evidence.top_python[:3])
            imports_summary = f"  ·  [#24d6a8]active:[/] {top}"
        provider_names = [
            f"[#24d6a8]{prov.name}[/]"
            for prov in self.diagnostics.providers
            if prov.status in ("found", "present") and prov.name != "Local deterministic"
        ]
        providers = " · ".join(provider_names) or "[#6e8aa1]no live providers[/]"
        line1 = (
            f"[#d9f7ff]{_join_or(p.languages, 'unknown')}[/] · "
            f"[#d9f7ff]{_join_or(p.package_managers, 'no pm')}[/] · "
            f"[#6e8aa1]{len(p.dependencies)} deps[/]"
            f"{imports_summary}"
        )
        line2 = f"[#6e8aa1]providers:[/] {providers}"
        return f"{line1}\n{line2}"

    # ------------------------------------------------------------------
    # Status / log helpers
    # ------------------------------------------------------------------

    def _set_status_banner(self, text: str, *, tone: str = "ok") -> None:
        banner = self.query_one("#status-banner", Static)
        for cls in ("warn", "info", "error"):
            banner.remove_class(cls)
        if tone in ("warn", "info", "error"):
            banner.add_class(tone)
        banner.update(text)

    def log_event(self, message: str, tone: str = "ok") -> None:
        log = self.query_one("#result-log", RichLog)
        ts = datetime.now().strftime("%H:%M:%S")
        color = {
            "ok": "#24d6a8",
            "info": "#7aa6ff",
            "warn": "#e3c26f",
            "error": "#ff6b6b",
            "muted": "#6e8aa1",
        }.get(tone, "#d9f7ff")
        log.write(f"[#25405c]{ts}[/] [{color}]{message}[/]")

    # ------------------------------------------------------------------
    # Modal/action helpers
    # ------------------------------------------------------------------

    def action_edit_repo(self) -> None:
        self.push_screen(
            RepoPathPromptScreen(self.diagnostics.repo),
            self._repo_path_chosen,
        )

    def _repo_path_chosen(self, value: str | None) -> None:
        if value is None:
            return
        new_path = Path(value).expanduser()
        try:
            resolved = new_path.resolve()
        except OSError:
            self._set_status_banner(f"Invalid path: {value}", tone="error")
            return
        if str(resolved) == self.diagnostics.repo:
            self._set_status_banner("Repo path unchanged.", tone="muted")
            return
        if not resolved.exists() or not resolved.is_dir():
            self._set_status_banner(f"Not a directory: {resolved}.", tone="error")
            return
        self._set_status_banner(f"Scanning {resolved}…", tone="info")
        self._refresh_diagnostics(resolved)

    @work(thread=True, exclusive=True)
    def _refresh_diagnostics(self, repo: Path) -> None:
        new_diag = setup_diagnostics(repo, scan_imports=True)
        self.call_from_thread(self._apply_diagnostics, new_diag)

    def _apply_diagnostics(self, new_diag: SetupDiagnostics) -> None:
        self.diagnostics = new_diag
        self.query_one("#brand-bar", Static).update(self._brand_bar_text())
        self.query_one("#analyse-bar", Static).update(self._analyse_bar_text())
        self._set_status_banner(
            f"Diagnostics refreshed for {new_diag.repo}", tone="ok"
        )
        self.log_event(f"Diagnostics refreshed for {new_diag.repo}", tone="muted")

    def _handle_picker_choice(self, value: str) -> None:
        """Called by the runner when the user picks a repo from the modal."""

        path = Path(value).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            self._set_status_banner(f"Invalid path: {value}", tone="error")
            return
        if not resolved.exists() or not resolved.is_dir():
            self._set_status_banner(f"Not a directory: {resolved}", tone="error")
            return
        self._set_status_banner(f"Scanning {resolved}…", tone="info")
        self._refresh_diagnostics(resolved)

    def action_open_diff(self) -> None:
        from frontier_scout.scout import run_scan
        from frontier_scout.store import previous_scan_verdicts

        current = run_scan(
            repo=Path(self.diagnostics.repo),
            dry_run=True,
            persist=False,
        ).get("verdicts") or []
        previous = previous_scan_verdicts(repo=self.diagnostics.repo)
        self.push_screen(DiffScreen(current=current, previous=previous))

    def action_request_quit(self) -> None:
        self.push_screen(QuitConfirmScreen(), self._handle_quit_choice)

    def _handle_quit_choice(self, decision: bool | None) -> None:
        if decision:
            self.exit()
        else:
            self._set_status_banner("Quit cancelled.", tone="muted")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_show_glossary(self) -> None:
        """v1.3.0 Stream B — bound to ?; explains every domain term."""

        from frontier_scout.tui.glossary import GlossaryScreen

        self.push_screen(GlossaryScreen())

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """v1.3.0 Stream B — refresh subtitle when the user switches tabs."""

        from frontier_scout.tui.glossary import TAB_SUBTITLES

        try:
            subtitle_widget = self.query_one("#tab-subtitle", Static)
        except Exception:  # noqa: BLE001 — pre-mount
            return
        slug = event.tab.id or ""
        # Textual prefixes the tab id with "--content-tab-" depending on
        # version; normalise to our tab slug.
        for candidate in (slug, slug.removeprefix("--content-tab-")):
            if candidate in TAB_SUBTITLES:
                subtitle_widget.update(TAB_SUBTITLES[candidate])
                return
        subtitle_widget.update("")

    def action_clear_log(self) -> None:
        self.query_one("#result-log", RichLog).clear()
        self.log_event("Log cleared.", tone="muted")

    def action_jump_tab(self, index: int) -> None:
        try:
            slug = TAB_SLUGS[index]
        except IndexError:
            return
        tc = self.query_one(TabbedContent)
        tc.active = slug

    def action_open_notifications(self) -> None:
        self.push_screen(NotificationsScreen(), self._notifications_closed)

    def _notifications_closed(self, _: object) -> None:
        self.query_one("#brand-bar", Static).update(self._brand_bar_text())

    def action_open_report(self) -> None:
        """Open the most recently rendered scout report for this repo,
        regenerating it from the latest persisted scan if needed."""

        from frontier_scout.report import render_html
        from frontier_scout.store import home_dir, latest_scan

        repo = Path(self.diagnostics.repo)
        report_dir = home_dir() / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        repo_id_path = report_dir / f"{repo.name}.html"
        # Codex #5: scope to *this* repo. Before v1.2.1 the TUI would render
        # whatever scan happened most recently across all repos.
        payload = latest_scan(repo=repo)
        if payload is None:
            self.log_event(
                f"No scout for {repo} yet — wait for the Scout tab to "
                "finish, then press r.",
                tone="warn",
            )
            return
        try:
            verdicts = list(payload.get("verdicts") or [])
            date = str(payload.get("date") or "latest")
            repo_id_path.write_text(render_html(verdicts, date=date, funnel=payload))
            webbrowser.open(repo_id_path.resolve().as_uri())
            self.log_event(f"Opened report: {repo_id_path}", tone="ok")
        except Exception as exc:  # noqa: BLE001
            self.log_event(f"Could not render report: {exc}", tone="error")


def _join_or(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback
