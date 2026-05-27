"""Textual mission-control setup app for Frontier Scout."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, OptionList, SelectionList, Static
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from frontier_scout.dependencies import run_dependency_scan
from frontier_scout.evaluate import evaluate_url
from frontier_scout.profile import build_scout_profile, export_profile, stack_from_profile
from frontier_scout.scout import run_scan
from frontier_scout.store import home_dir, read_setup_state, save_repo_profile, write_setup_state
from frontier_scout.tui.setup_diagnostics import SetupDiagnostics, setup_diagnostics


class SetupApp(App[None]):
    """Polished first-run setup app with conservative safe actions."""

    CSS = """
    Screen {
        background: #071019;
        color: #d9f7ff;
    }

    #root {
        padding: 1 2;
        height: 100%;
    }

    .hero {
        border: round #24d6a8;
        padding: 1 2;
        margin-bottom: 1;
        background: #0b1621;
    }

    #mission-title {
        text-style: bold;
        color: #ffffff;
    }

    #repo-input {
        margin-bottom: 1;
        border: round #2b5c78;
    }

    .panel-row {
        height: 14;
    }

    .panel {
        border: round #2b5c78;
        padding: 1 2;
        background: #091520;
        height: 1fr;
    }

    .panel-title {
        text-style: bold;
        color: #8af7c8;
        margin-bottom: 1;
    }

    #packs {
        border: none;
        height: 1fr;
        background: #091520;
    }

    #actions {
        border: none;
        height: 6;
    }

    #tool-url {
        margin-top: 1;
        border: round #2b5c78;
    }

    #result {
        border: round #24d6a8;
        padding: 1 2;
        height: 6;
        margin-top: 1;
        background: #08131d;
    }

    #help {
        border: round #e3c26f;
        padding: 1 2;
        height: auto;
        margin-top: 1;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("q", "request_quit", "Quit"),
        ("?", "toggle_help", "Help"),
        ("/", "focus_url", "URL"),
        ("escape", "hide_help", "Back"),
    ]

    def __init__(self, diagnostics: SetupDiagnostics) -> None:
        super().__init__()
        self.diagnostics = diagnostics
        self._quit_requested = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="root"):
            with Vertical(classes="hero"):
                yield Label("Frontier Scout Mission Control", id="mission-title")
                yield Static("Scout -> Fit -> Risk -> Trial -> Guard")
                yield Static("Local-first setup. No repo content sent to an LLM. No tools installed.")
            yield Input(value=self.diagnostics.repo, placeholder="repo path", id="repo-input")
            with Horizontal(classes="panel-row"):
                with Vertical(classes="panel"):
                    yield Label("Repo Fingerprint", classes="panel-title")
                    yield Static(self._fingerprint_text(), id="fingerprint")
                with Vertical(classes="panel"):
                    yield Label("Providers", classes="panel-title")
                    yield Static(self._provider_text(), id="providers")
                with Vertical(classes="panel"):
                    yield Label("Scout Packs (space to toggle)", classes="panel-title")
                    yield SelectionList[str](
                        *self._pack_selections(),
                        id="packs",
                    )
            with Vertical(classes="panel"):
                yield Label("Safe First Run", classes="panel-title")
                yield OptionList(
                    *self._action_options(),
                    id="actions",
                )
                yield Input(placeholder="Paste a tool URL for evaluate", id="tool-url")
            yield Static(
                "Select an action and press Enter. Nothing writes into the repo unless you choose it.",
                id="result",
            )
            yield Static(
                "Keys: arrows move, Enter runs, space toggles packs, / focuses URL, ? toggles help, Esc hides help, q quits.",
                id="help",
                classes="hidden",
            )
        yield Footer()

    def on_mount(self) -> None:
        if self.size.width < 100 or self.size.height < 26:
            self.query_one("#result", Static).update(
                "Terminal is small. Resize for the full mission-control layout, or run: frontier-scout setup --plain"
            )
        self.query_one("#actions", OptionList).focus()

    @on(OptionList.OptionSelected, "#actions")
    def run_selected_action(self, event: OptionList.OptionSelected) -> None:
        action_id = str(event.option_id)
        self._run_action(action_id)

    @on(SelectionList.SelectedChanged, "#packs")
    def packs_changed(self) -> None:
        selected = list(self.query_one("#packs", SelectionList).selected)
        self.diagnostics.scout_packs_selected = selected
        state = read_setup_state()
        state["selected_packs"] = selected
        write_setup_state(state)

    @on(Input.Submitted, "#repo-input")
    def repo_submitted(self, event: Input.Submitted) -> None:
        new_path = Path(event.value).expanduser()
        if str(new_path.resolve()) == self.diagnostics.repo:
            return
        if not new_path.exists() or not new_path.is_dir():
            self.query_one("#result", Static).update(
                f"Path is not a directory: {new_path}. Keeping previous diagnostics."
            )
            return
        self.query_one("#result", Static).update(f"Rebuilding diagnostics for {new_path}...")
        self._refresh_diagnostics(new_path)

    @work(thread=True, exclusive=True)
    def _refresh_diagnostics(self, repo: Path) -> None:
        selected = list(self.diagnostics.scout_packs_selected)
        new_diag = setup_diagnostics(repo, selected_packs=selected, scan_imports=True)
        self.call_from_thread(self._apply_diagnostics, new_diag)

    def _apply_diagnostics(self, new_diag: SetupDiagnostics) -> None:
        self.diagnostics = new_diag
        self.query_one("#fingerprint", Static).update(self._fingerprint_text())
        self.query_one("#providers", Static).update(self._provider_text())
        actions = self.query_one("#actions", OptionList)
        actions.clear_options()
        for option in self._action_options():
            actions.add_option(option)
        self.query_one("#result", Static).update(f"Diagnostics updated for {new_diag.repo}.")

    def action_request_quit(self) -> None:
        if self._quit_requested:
            self.exit()
            return
        self._quit_requested = True
        self.query_one("#result", Static).update("Quit requested. Press q again to exit, or Esc to keep setup open.")

    def action_toggle_help(self) -> None:
        help_panel = self.query_one("#help", Static)
        help_panel.toggle_class("hidden")

    def action_hide_help(self) -> None:
        self._quit_requested = False
        self.query_one("#help", Static).add_class("hidden")

    def action_focus_url(self) -> None:
        self.query_one("#tool-url", Input).focus()

    def _run_action(self, action_id: str) -> None:
        result = self.query_one("#result", Static)
        repo = Path(self.diagnostics.repo)
        if action_id == "profile":
            profile = build_scout_profile(repo)
            save_repo_profile(profile)
            path = export_profile(profile, home_dir() / "profiles" / f"{profile.repo_id}.json")
            result.update(f"Profile written locally: {path}")
            return
        if action_id == "dry_scan":
            payload = run_scan(repo=repo, dry_run=True, persist=True)
            result.update(
                f"Dry scan complete: {len(payload.get('verdicts', []))} verdicts. Next: frontier-scout report"
            )
            return
        if action_id == "deps_scan":
            payload = run_dependency_scan(repo)
            result.update(f"Dependency scan complete: {len(payload.get('findings', []))} finding(s).")
            return
        if action_id == "evaluate_url":
            url = self.query_one("#tool-url", Input).value.strip()
            if not url:
                result.update("Paste a tool URL first, then select Evaluate pasted tool URL.")
                self.query_one("#tool-url", Input).focus()
                return
            profile = build_scout_profile(repo)
            evaluation = evaluate_url(url, stack_from_profile(profile))
            result.update(
                f"Evaluation: {evaluation.tool_name} | fit={evaluation.fit} | risk={evaluation.risk} | "
                f"next=frontier-scout trial {evaluation.tool_name} --dry-run"
            )
            return
        if action_id == "demo_report":
            result.update("Run the stable offline demo with: frontier-scout demo")
            return
        result.update("Unknown action.")

    def _fingerprint_text(self) -> str:
        profile = self.diagnostics.profile
        deps = ", ".join(f"{dep.name}{dep.specifier}" for dep in profile.dependencies[:3])
        lines = [
            f"repo: {profile.repo}",
            f"languages: {_join_or(profile.languages, 'unknown')}",
            f"packages: {_join_or(profile.package_managers, 'none')}",
            f"containers: {_join_or(profile.containers, 'none')}",
            f"ci: {_join_or(profile.ci, 'none')}",
            f"agent configs: {_join_or(profile.agent_configs, 'none')}",
            f"dependencies: {deps or 'none detected'}",
        ]
        evidence = profile.import_evidence
        if evidence.available and (evidence.top_python or evidence.top_javascript):
            top_py = ", ".join(f"{name}×{count}" for name, count in evidence.top_python[:3])
            top_js = ", ".join(f"{name}×{count}" for name, count in evidence.top_javascript[:2])
            parts = [p for p in (top_py, top_js) if p]
            lines.append(f"imports: {' · '.join(parts)}" if parts else "imports: none detected")
        return "\n".join(lines)

    def _provider_text(self) -> str:
        lines = []
        for provider in self.diagnostics.providers:
            model_hint = f" [{', '.join(provider.models[:2])}]" if provider.models else ""
            lines.append(f"{provider.name}: {provider.status}{model_hint}")
        return "\n".join(lines)

    def _pack_selections(self) -> list[Selection[str]]:
        selected = set(self.diagnostics.scout_packs_selected)
        return [
            Selection(pack, pack, initial_state=pack in selected)
            for pack in self.diagnostics.scout_packs
        ]

    def _action_options(self) -> list[Option]:
        return [
            Option(f"{action.label}\n  {action.description}", id=action.id)
            for action in self.diagnostics.recommended_actions
        ]


def _join_or(items: list[str], fallback: str) -> str:
    return ", ".join(items) if items else fallback
