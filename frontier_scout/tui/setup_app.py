"""Mission Control v2 — the redesigned Textual setup app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, RichLog, SelectionList, Static
from textual.widgets.selection_list import Selection

from frontier_scout import __version__
from frontier_scout.dependencies import run_dependency_scan
from frontier_scout.evaluate import evaluate_url
from frontier_scout.profile import build_scout_profile, export_profile, stack_from_profile
from frontier_scout.scout import run_scan
from frontier_scout.store import home_dir, read_setup_state, save_repo_profile, write_setup_state
from frontier_scout.tui.modals import HelpScreen, QuitConfirmScreen, RepoPathPromptScreen
from frontier_scout.tui.setup_diagnostics import SetupDiagnostics, setup_diagnostics


_BAR_GLYPHS = "▁▂▃▄▅▆▇█"


def _evidence_bar(count: int, peak: int) -> str:
    if peak <= 0:
        return ""
    ratio = min(count / peak, 1.0)
    filled = max(1, round(ratio * 10))
    return _BAR_GLYPHS[-1] * filled


class SetupApp(App[None]):
    """First-run mission control with a designer-aligned brand."""

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

    #brand-bar .brand-mark {
        color: #24d6a8;
        text-style: bold;
    }

    #brand-bar .brand-version {
        color: #6e8aa1;
    }

    #brand-bar .brand-tag {
        color: #6e8aa1;
    }

    #brand-bar .brand-repo {
        color: #7aa6ff;
    }

    #status-banner {
        height: 1;
        padding: 0 2;
        background: #0d1622;
        color: #24d6a8;
    }

    #status-banner.warn {
        color: #e3c26f;
    }

    #status-banner.info {
        color: #7aa6ff;
    }

    #status-banner.error {
        color: #ff6b6b;
    }

    #body {
        padding: 1 1;
    }

    .panel-row {
        height: 18;
        margin-bottom: 1;
    }

    .panel {
        border: round #25405c;
        padding: 0 1;
        background: #0d1622;
        width: 1fr;
    }

    .panel:focus-within {
        border: round #24d6a8;
    }

    .panel-title {
        text-style: bold;
        color: #d9f7ff;
        padding: 0 1;
        margin-top: 0;
    }

    VerticalScroll {
        height: 1fr;
    }

    #fingerprint, #providers {
        color: #d9f7ff;
        padding: 0 1;
    }

    #fingerprint .label {
        color: #6e8aa1;
    }

    #fingerprint .ev-name {
        color: #24d6a8;
    }

    #fingerprint .ev-bar {
        color: #24d6a8;
    }

    #providers .ok {
        color: #24d6a8;
        text-style: bold;
    }

    #providers .warn {
        color: #e3c26f;
    }

    #providers .miss {
        color: #6e8aa1;
    }

    #packs {
        background: #0d1622;
    }

    .actions-row {
        height: 3;
        margin-bottom: 1;
    }

    .actions-row Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    .actions-row Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
        text-style: bold;
    }

    #url-row {
        height: auto;
        margin-bottom: 1;
    }

    #url-row.hidden {
        display: none;
    }

    #tool-url {
        border: round #25405c;
    }

    #tool-url:focus {
        border: round #7aa6ff;
    }

    #result-log {
        height: 1fr;
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
    ]

    def __init__(self, diagnostics: SetupDiagnostics, *, show_splash: bool = True) -> None:
        super().__init__()
        self.diagnostics = diagnostics
        self._show_splash = show_splash

    # ------------------------------------------------------------------
    # Compose / mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(self._brand_bar_text(), id="brand-bar", markup=True)
        yield Static(
            "Local-first. No repo content sent to an LLM. No tools installed.",
            id="status-banner",
        )
        with Vertical(id="body"):
            with Horizontal(classes="panel-row"):
                with Vertical(classes="panel", id="panel-fingerprint"):
                    yield Label("Repo Fingerprint", classes="panel-title")
                    with VerticalScroll():
                        yield Static(self._fingerprint_text(), id="fingerprint", markup=True)
                with Vertical(classes="panel", id="panel-providers"):
                    yield Label("Providers", classes="panel-title")
                    with VerticalScroll():
                        yield Static(self._provider_text(), id="providers", markup=True)
                with Vertical(classes="panel", id="panel-packs"):
                    yield Label("Scout Packs · space toggles", classes="panel-title")
                    yield SelectionList[str](*self._pack_selections(), id="packs")
            with Horizontal(classes="actions-row"):
                for action in self.diagnostics.recommended_actions:
                    yield Button(action.label, id=f"action-{action.id}")
            with Container(id="url-row", classes="hidden"):
                yield Input(placeholder="Paste a tool URL, press Enter to evaluate", id="tool-url")
            yield RichLog(id="result-log", markup=True, auto_scroll=True, wrap=True)

    def on_mount(self) -> None:
        if self._show_splash:
            from frontier_scout.tui.splash import SplashScreen

            self.push_screen(SplashScreen())
        self._set_status_banner(
            "Local-first. No repo content sent to an LLM. No tools installed.", tone="ok"
        )
        if self.size.width < 110 or self.size.height < 28:
            self._set_status_banner(
                "Terminal is small — resize for the full layout, or run: frontier-scout setup --plain",
                tone="warn",
            )
        self._log_event(
            f"Ready · repo {self.diagnostics.repo}",
            tone="muted",
        )
        # Land focus on the first action button so Enter immediately runs the lead action.
        first_button = self.query("Button").first(Button)
        if first_button is not None:
            first_button.focus()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _brand_bar_text(self) -> str:
        repo = self.diagnostics.repo
        return (
            f"[#24d6a8 bold]◉ FRONTIER · SCOUT[/]  "
            f"[#6e8aa1]v{__version__}[/]   "
            f"[#6e8aa1]try-before-trust radar[/]"
            f"   [#7aa6ff]📁 {repo}[/]"
        )

    def _fingerprint_text(self) -> str:
        profile = self.diagnostics.profile
        deps_head = ", ".join(
            f"{dep.name}{dep.specifier}" for dep in profile.dependencies[:3]
        ) or "none detected"
        lines = [
            f"[#6e8aa1]languages   [/] {_join_or(profile.languages, 'unknown')}",
            f"[#6e8aa1]packages    [/] {_join_or(profile.package_managers, 'none')}",
            f"[#6e8aa1]containers  [/] {_join_or(profile.containers, 'none')}",
            f"[#6e8aa1]ci          [/] {_join_or(profile.ci, 'none')}",
            f"[#6e8aa1]agent cfg   [/] {_join_or(profile.agent_configs, 'none')}",
            f"[#6e8aa1]deps        [/] {len(profile.dependencies)} ({deps_head})",
        ]
        evidence = profile.import_evidence
        if evidence.available and (evidence.top_python or evidence.top_javascript):
            lines.append("")
            lines.append("[#d9f7ff bold]Active imports[/]")
            peak = max(
                (count for _, count in evidence.top_python[:5]),
                default=0,
            ) or max(
                (count for _, count in evidence.top_javascript[:5]),
                default=0,
            )
            for name, count in evidence.top_python[:5]:
                bar = _evidence_bar(count, peak)
                lines.append(f"  [#24d6a8]{name:<22}[/] [#24d6a8]{bar}[/] [#6e8aa1]×{count}[/]")
            for name, count in evidence.top_javascript[:3]:
                bar = _evidence_bar(count, peak)
                lines.append(f"  [#7aa6ff]{name:<22}[/] [#7aa6ff]{bar}[/] [#6e8aa1]×{count}[/]")
            partial = " [#e3c26f](partial)[/]" if evidence.partial else ""
            lines.append(f"  [#6e8aa1]files scanned: {evidence.files_scanned}[/]{partial}")
        elif not evidence.available:
            lines.append("")
            lines.append("[#e3c26f]Import scanner unavailable (tree-sitter not installed)[/]")
        return "\n".join(lines)

    def _provider_text(self) -> str:
        lines = []
        for provider in self.diagnostics.providers:
            status = provider.status
            if status in ("found", "present"):
                dot = "[#24d6a8 bold]●[/]"
            elif status in ("unavailable", "error"):
                dot = "[#e3c26f]●[/]"
            else:
                dot = "[#6e8aa1]●[/]"
            lines.append(f"{dot} [#d9f7ff]{provider.name:<20}[/] [#6e8aa1]{status}[/]")
            if provider.models:
                shown = ", ".join(provider.models[:2])
                lines.append(f"  [#6e8aa1]models: {shown}[/]")
        return "\n".join(lines)

    def _pack_selections(self) -> list[Selection[str]]:
        selected = set(self.diagnostics.scout_packs_selected)
        return [
            Selection(pack, pack, initial_state=pack in selected)
            for pack in self.diagnostics.scout_packs
        ]

    # ------------------------------------------------------------------
    # Status banner + log helpers
    # ------------------------------------------------------------------

    def _set_status_banner(self, text: str, *, tone: str = "ok") -> None:
        banner = self.query_one("#status-banner", Static)
        banner.remove_class("warn")
        banner.remove_class("info")
        banner.remove_class("error")
        if tone == "warn":
            banner.add_class("warn")
        elif tone == "info":
            banner.add_class("info")
        elif tone == "error":
            banner.add_class("error")
        banner.update(text)

    def _log_event(self, message: str, *, tone: str = "ok") -> None:
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
    # Selection persistence
    # ------------------------------------------------------------------

    @on(SelectionList.SelectedChanged, "#packs")
    def packs_changed(self) -> None:
        selected = list(self.query_one("#packs", SelectionList).selected)
        self.diagnostics.scout_packs_selected = selected
        state = read_setup_state()
        state["selected_packs"] = selected
        write_setup_state(state)
        self._log_event(
            f"Packs updated: {', '.join(selected) if selected else 'none'}",
            tone="muted",
        )

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id is None or not event.button.id.startswith("action-"):
            return
        action_id = event.button.id.removeprefix("action-")
        self._run_action(action_id)

    def _run_action(self, action_id: str) -> None:
        repo = Path(self.diagnostics.repo)
        if action_id == "profile":
            profile = build_scout_profile(repo)
            save_repo_profile(profile)
            path = export_profile(profile, home_dir() / "profiles" / f"{profile.repo_id}.json")
            self._log_event(f"Profile written: {path}", tone="ok")
            return
        if action_id == "dry_scan":
            payload = run_scan(repo=repo, dry_run=True, persist=True)
            count = len(payload.get("verdicts", []))
            self._log_event(
                f"Dry scan complete · {count} verdicts. Next: frontier-scout report",
                tone="ok",
            )
            return
        if action_id == "deps_scan":
            payload = run_dependency_scan(repo)
            count = len(payload.get("findings", []))
            self._log_event(
                f"Dependency scan complete · {count} finding(s).",
                tone="ok",
            )
            return
        if action_id == "evaluate_url":
            self._expand_url_row()
            url_input = self.query_one("#tool-url", Input)
            url = url_input.value.strip()
            if not url:
                self._set_status_banner(
                    "Paste a tool URL into the field below, then press Enter.",
                    tone="info",
                )
                url_input.focus()
                return
            profile = build_scout_profile(repo)
            evaluation = evaluate_url(url, stack_from_profile(profile))
            self._log_event(
                f"Evaluate · {evaluation.tool_name} fit={evaluation.fit} risk={evaluation.risk}",
                tone="ok",
            )
            return
        if action_id == "demo_report":
            self._log_event(
                "Run the stable offline demo with: frontier-scout demo",
                tone="info",
            )
            return
        self._log_event(f"Unknown action: {action_id}", tone="error")

    def _expand_url_row(self) -> None:
        row = self.query_one("#url-row", Container)
        row.remove_class("hidden")

    @on(Input.Submitted, "#tool-url")
    def on_url_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        if not url:
            self._set_status_banner("URL is empty.", tone="warn")
            return
        repo = Path(self.diagnostics.repo)
        profile = build_scout_profile(repo)
        evaluation = evaluate_url(url, stack_from_profile(profile))
        self._log_event(
            f"Evaluate · {evaluation.tool_name} fit={evaluation.fit} risk={evaluation.risk}",
            tone="ok",
        )

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
                f"Not a directory: {resolved}. Keeping previous diagnostics.",
                tone="error",
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
        self.query_one("#fingerprint", Static).update(self._fingerprint_text())
        self.query_one("#providers", Static).update(self._provider_text())
        # Recommended-action ordering is derived from providers (env-vars +
        # locally detected runtimes), which do not change across repo path
        # refreshes inside one session — so the action strip stays stable
        # rather than racing on remove/remount.
        self._set_status_banner(
            f"Diagnostics refreshed for {new_diag.repo}", tone="ok"
        )
        self._log_event(f"Diagnostics refreshed for {new_diag.repo}", tone="muted")

    # ------------------------------------------------------------------
    # Quit / help / log clear
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
        self._log_event("Log cleared.", tone="muted")


def _join_or(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback
