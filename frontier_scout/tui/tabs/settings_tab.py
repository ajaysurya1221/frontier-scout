"""Settings tab — policy, environment, and system state (read-only-ish)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static

from frontier_scout import __version__
from frontier_scout.policy import default_policy_toml
from frontier_scout.store import home_dir, read_setup_state, write_setup_state


class SettingsTab(VerticalScroll):
    """Three panels: Policy, Environment, System."""

    DEFAULT_CSS = """
    SettingsTab .settings-section {
        border: round #25405c;
        padding: 1 2;
        margin-bottom: 1;
        background: #0d1622;
    }

    SettingsTab .settings-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    SettingsTab Button {
        margin-right: 1;
        margin-top: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    SettingsTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    SettingsTab .muted {
        color: #6e8aa1;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        with Vertical(classes="settings-section"):
            yield Label("Policy", classes="settings-title")
            yield Static(self._policy_text(), id="policy-text", markup=True)
            with Horizontal():
                yield Button("Init policy (home)", id="settings-policy-home")
                yield Button("Init policy (repo)", id="settings-policy-repo")
        with Vertical(classes="settings-section"):
            yield Label("Environment", classes="settings-title")
            yield Static(self._env_text(), id="settings-env-text", markup=True)
        with Vertical(classes="settings-section"):
            yield Label("System", classes="settings-title")
            yield Static(self._system_text(), id="settings-system-text", markup=True)
            with Horizontal():
                yield Button("Reset setup state", id="settings-reset-state")

    @on(Button.Pressed, "#settings-policy-home")
    def _init_policy_home(self) -> None:
        path = home_dir() / "policy.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_policy_toml())
        self.query_one("#policy-text", Static).update(self._policy_text())
        self.app_ref.log_event(f"Policy written to {path}", tone="ok")

    @on(Button.Pressed, "#settings-policy-repo")
    def _init_policy_repo(self) -> None:
        repo = Path(self.app_ref.diagnostics.repo)
        path = repo / ".frontier-scout" / "policy.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_policy_toml())
        self.query_one("#policy-text", Static).update(self._policy_text())
        self.app_ref.log_event(f"Policy written to {path}", tone="ok")

    @on(Button.Pressed, "#settings-reset-state")
    def _reset_state(self) -> None:
        write_setup_state({})
        self.query_one("#settings-system-text", Static).update(self._system_text())
        self.app_ref.log_event("Setup state cleared.", tone="warn")

    def _policy_text(self) -> str:
        candidates = [
            home_dir() / "policy.toml",
            Path(self.app_ref.diagnostics.repo) / ".frontier-scout" / "policy.toml",
        ]
        existing = [p for p in candidates if p.exists()]
        if not existing:
            return (
                "[#6e8aa1]No policy file found.[/]\n"
                "[#6e8aa1]Use 'Init policy' to write a conservative default.[/]"
            )
        lines = []
        for path in existing:
            lines.append(f"[#24d6a8]{path}[/]")
            try:
                preview = path.read_text(errors="ignore")[:600]
                lines.append(preview)
            except OSError:
                lines.append("[#e3c26f]unreadable[/]")
            lines.append("")
        return "\n".join(lines)

    def _env_text(self) -> str:
        rows = []
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "JUDGE_ENABLED"):
            present = bool(os.environ.get(var))
            dot = "[#24d6a8 bold]●[/]" if present else "[#6e8aa1]●[/]"
            state = "present" if present else "missing"
            rows.append(f"{dot}  [#d9f7ff]{var:<22}[/] [#6e8aa1]{state}[/]")
        rows.append("")
        rows.append("[#6e8aa1]Values are never read or shown; only presence is checked.[/]")
        return "\n".join(rows)

    def _system_text(self) -> str:
        state = read_setup_state()
        state_pretty = json.dumps(state, indent=2, sort_keys=True) if state else "{}"
        return "\n".join(
            [
                f"[#6e8aa1]version:    [/] [#d9f7ff]frontier-scout {__version__}[/]",
                f"[#6e8aa1]home:       [/] [#d9f7ff]{home_dir()}[/]",
                f"[#6e8aa1]repo:       [/] [#d9f7ff]{self.app_ref.diagnostics.repo}[/]",
                "",
                "[#d9f7ff bold]setup_state.json[/]",
                state_pretty,
            ]
        )
