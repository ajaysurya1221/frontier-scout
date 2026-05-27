"""Mission Control v1 — tabbed, scout-first, all-features-in-one-screen."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import RichLog, Static, TabbedContent, TabPane

from frontier_scout import __version__
from frontier_scout.tui.modals import HelpScreen, QuitConfirmScreen, RepoPathPromptScreen
from frontier_scout.tui.setup_diagnostics import SetupDiagnostics, setup_diagnostics
from frontier_scout.tui.tabs import DEFAULT_TAB, TAB_REGISTRY, TAB_SLUGS
from frontier_scout.tui.tabs.deps_tab import DepsTab
from frontier_scout.tui.tabs.guard_tab import GuardTab
from frontier_scout.tui.tabs.incident_tab import IncidentTab
from frontier_scout.tui.tabs.packs_tab import PacksTab
from frontier_scout.tui.tabs.receipts_tab import ReceiptsTab
from frontier_scout.tui.tabs.reports_tab import ReportsTab
from frontier_scout.tui.tabs.scout_tab import ScoutTab
from frontier_scout.tui.tabs.settings_tab import SettingsTab
from frontier_scout.tui.tabs.trials_tab import TrialsTab


class SetupApp(App[None]):
    """The v1 tabbed Mission Control."""

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

    Tabs {
        background: #0d1622;
    }

    Tab {
        color: #6e8aa1;
    }

    Tab.-active {
        color: #24d6a8;
        text-style: bold;
    }

    #result-log {
        height: 8;
        border: round #25405c;
        background: #0d1622;
        color: #d9f7ff;
    }

    #result-log:focus-within {
        border: round #24d6a8;
    }
    """

    BINDINGS: ClassVar = [
        Binding("q", "request_quit", "Quit"),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("?", "show_help", "Help"),
        Binding("slash", "edit_repo", "Repo path"),
        Binding("/", "edit_repo", "Repo path"),
        Binding("ctrl+l", "clear_log", "Clear log"),
        Binding("1", "jump_tab(0)", "Scout", show=False),
        Binding("2", "jump_tab(1)", "Trials", show=False),
        Binding("3", "jump_tab(2)", "Receipts", show=False),
        Binding("4", "jump_tab(3)", "Guard", show=False),
        Binding("5", "jump_tab(4)", "Reports", show=False),
        Binding("6", "jump_tab(5)", "Packs", show=False),
        Binding("7", "jump_tab(6)", "Deps", show=False),
        Binding("8", "jump_tab(7)", "Incident", show=False),
        Binding("9", "jump_tab(8)", "Settings", show=False),
    ]

    def __init__(
        self,
        diagnostics: SetupDiagnostics,
        *,
        show_splash: bool = True,
        initial_tab: str = DEFAULT_TAB,
    ) -> None:
        super().__init__()
        self.diagnostics = diagnostics
        self._show_splash = show_splash
        self._initial_tab = initial_tab if initial_tab in TAB_SLUGS else DEFAULT_TAB

    # ------------------------------------------------------------------
    # Compose / mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(self._brand_bar_text(), id="brand-bar", markup=True)
        yield Static(
            "Local-first. No repo content sent to an LLM. No tools installed.",
            id="status-banner",
        )
        yield Static(self._analyse_bar_text(), id="analyse-bar", markup=True)
        with TabbedContent(initial=self._initial_tab):
            for spec in TAB_REGISTRY:
                with TabPane(spec.title, id=spec.slug):
                    yield self._build_tab(spec.slug)
        yield RichLog(id="result-log", markup=True, auto_scroll=True, wrap=True)

    def _build_tab(self, slug: str) -> Container:
        mapping = {
            "scout": ScoutTab,
            "trials": TrialsTab,
            "receipts": ReceiptsTab,
            "guard": GuardTab,
            "reports": ReportsTab,
            "packs": PacksTab,
            "deps": DepsTab,
            "incident": IncidentTab,
            "settings": SettingsTab,
        }
        cls = mapping[slug]
        return cls(self)

    def on_mount(self) -> None:
        if self._show_splash:
            from frontier_scout.tui.splash import SplashScreen

            self.push_screen(SplashScreen())
        self._set_status_banner(
            "Local-first. No repo content sent to an LLM. No tools installed.",
            tone="ok",
        )
        if self.size.width < 110 or self.size.height < 30:
            self._set_status_banner(
                "Terminal is small — resize for the full layout, or run: frontier-scout setup --plain",
                tone="warn",
            )
        self.log_event(f"Ready · repo {self.diagnostics.repo}", tone="muted")

    # ------------------------------------------------------------------
    # Bars
    # ------------------------------------------------------------------

    def _brand_bar_text(self) -> str:
        return (
            f"[#24d6a8 bold]◉ FRONTIER · SCOUT[/]  "
            f"[#6e8aa1]v{__version__}[/]   "
            f"[#6e8aa1]the radar for latest AI releases that fit your repo[/]   "
            f"[#7aa6ff]📁 {self.diagnostics.repo}[/]"
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
    # Status / log helpers (called by tabs)
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
    # Repo-path modal
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
            self._set_status_banner(
                f"Not a directory: {resolved}.", tone="error"
            )
            return
        self._set_status_banner(f"Scanning {resolved}…", tone="info")
        self._refresh_diagnostics(resolved)

    @work(thread=True, exclusive=True)
    def _refresh_diagnostics(self, repo: Path) -> None:
        selected = list(self.diagnostics.scout_packs_selected)
        new_diag = setup_diagnostics(repo, selected_packs=selected, scan_imports=True)
        self.call_from_thread(self._apply_diagnostics, new_diag)

    def _apply_diagnostics(self, new_diag: SetupDiagnostics) -> None:
        self.diagnostics = new_diag
        self.query_one("#brand-bar", Static).update(self._brand_bar_text())
        self.query_one("#analyse-bar", Static).update(self._analyse_bar_text())
        self._set_status_banner(
            f"Diagnostics refreshed for {new_diag.repo}", tone="ok"
        )
        self.log_event(f"Diagnostics refreshed for {new_diag.repo}", tone="muted")

    # ------------------------------------------------------------------
    # Quit / help / log / tab jumps
    # ------------------------------------------------------------------

    def action_request_quit(self) -> None:
        self.push_screen(QuitConfirmScreen(), self._handle_quit_choice)

    def _handle_quit_choice(self, decision: bool | None) -> None:
        if decision:
            self.exit()
        else:
            self._set_status_banner("Quit cancelled.", tone="muted")

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

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


def _join_or(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback
