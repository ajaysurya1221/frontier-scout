"""Settings tab — v1.2.

Policy / Environment / Memory / Automation / System panels. Every render
and every button handler is wrapped in try/except so a broken filesystem
or missing helper never crashes the tab.
"""

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


def _safe(generator):
    """Decorator that runs ``generator`` and returns a friendly error
    string instead of crashing the tab if it raises."""

    try:
        return generator()
    except Exception as exc:  # noqa: BLE001 — defensive, never crash the tab.
        return f"[#ff6b6b]rendering error: {exc}[/]"


class SettingsTab(VerticalScroll):
    """Five defensive panels."""

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
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        with Vertical(classes="settings-section"):
            yield Label("Policy", classes="settings-title")
            yield Static(_safe(self._policy_text), id="policy-text", markup=True)
            with Horizontal():
                yield Button("Init policy (home)", id="settings-policy-home")
                yield Button("Init policy (repo)", id="settings-policy-repo")
        with Vertical(classes="settings-section"):
            yield Label("Environment", classes="settings-title")
            yield Static(_safe(self._env_text), id="settings-env-text", markup=True)
        with Vertical(classes="settings-section"):
            yield Label("Memory", classes="settings-title")
            yield Static(_safe(self._memory_text), id="settings-memory-text", markup=True)
            with Horizontal():
                yield Button("Clear for this repo", id="settings-memory-repo")
                yield Button("Clear all repos", id="settings-memory-all")
        with Vertical(classes="settings-section"):
            yield Label("Automation", classes="settings-title")
            yield Static(_safe(self._automation_text), id="settings-automation-text", markup=True)
            with Horizontal():
                yield Button("Open setup wizard", id="settings-wizard")
        with Vertical(classes="settings-section"):
            yield Label("System", classes="settings-title")
            yield Static(_safe(self._system_text), id="settings-system-text", markup=True)
            with Horizontal():
                yield Button("Reset setup state", id="settings-reset-state")

    # ------------------------------------------------------------------
    # Handlers — wrapped so a broken filesystem never crashes the tab.
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#settings-policy-home")
    def _init_policy_home(self) -> None:
        try:
            path = home_dir() / "policy.toml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_policy_toml())
            self.query_one("#policy-text", Static).update(_safe(self._policy_text))
            self.app_ref.log_event(f"Policy written to {path}", tone="ok")
        except Exception as exc:  # noqa: BLE001
            self.app_ref.log_event(f"Could not write policy: {exc}", tone="error")

    @on(Button.Pressed, "#settings-policy-repo")
    def _init_policy_repo(self) -> None:
        try:
            repo = Path(self.app_ref.diagnostics.repo)
            path = repo / ".frontier-scout" / "policy.toml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_policy_toml())
            self.query_one("#policy-text", Static).update(_safe(self._policy_text))
            self.app_ref.log_event(f"Policy written to {path}", tone="ok")
        except Exception as exc:  # noqa: BLE001
            self.app_ref.log_event(f"Could not write policy: {exc}", tone="error")

    @on(Button.Pressed, "#settings-reset-state")
    def _reset_state(self) -> None:
        try:
            write_setup_state({})
            self.query_one("#settings-system-text", Static).update(_safe(self._system_text))
            self.app_ref.log_event("Setup state cleared.", tone="warn")
        except Exception as exc:  # noqa: BLE001
            self.app_ref.log_event(f"Reset failed: {exc}", tone="error")

    @on(Button.Pressed, "#settings-memory-repo")
    def _clear_memory_repo(self) -> None:
        try:
            from frontier_scout.store import clear_scans_for_repo

            repo = self.app_ref.diagnostics.repo
            removed = clear_scans_for_repo(repo)
            self.app_ref.log_event(
                f"Cleared {removed} scan(s) for this repo.", tone="warn"
            )
            self.query_one("#settings-memory-text", Static).update(_safe(self._memory_text))
        except Exception as exc:  # noqa: BLE001
            self.app_ref.log_event(f"Memory clear failed: {exc}", tone="error")

    @on(Button.Pressed, "#settings-memory-all")
    def _clear_memory_all(self) -> None:
        try:
            from frontier_scout.store import clear_all_scans

            removed = clear_all_scans()
            self.app_ref.log_event(
                f"Cleared {removed} scan(s) across all repos.", tone="warn"
            )
            self.query_one("#settings-memory-text", Static).update(_safe(self._memory_text))
        except Exception as exc:  # noqa: BLE001
            self.app_ref.log_event(f"Memory clear failed: {exc}", tone="error")

    @on(Button.Pressed, "#settings-wizard")
    def _open_wizard(self) -> None:
        """Stream N — exit the TUI with the reconfigure sentinel
        (``cli.RECONFIGURE_EXIT_CODE``). ``cli.main`` catches this and
        launches the wizard, then re-enters the TUI. Falls back to the
        old "quit and run setup" message if the parent app isn't the
        SetupApp we expect (e.g. embedded use)."""

        try:
            from frontier_scout.cli import RECONFIGURE_EXIT_CODE

            self.app_ref.log_event(
                "Relaunching wizard — your existing config and schedules are preserved.",
                tone="info",
            )
            self.app_ref.exit(return_code=RECONFIGURE_EXIT_CODE)
        except Exception:  # noqa: BLE001 — defensive fallback
            self.app_ref.log_event(
                "Quit (q), then run `frontier-scout setup --force` to re-run the wizard.",
                tone="info",
            )

    # ------------------------------------------------------------------
    # Renderers — every one tolerates missing files / dirs / state.
    # ------------------------------------------------------------------

    def _memory_text(self) -> str:
        return (
            "[#6e8aa1]Stored scan history lives in ~/.frontier-scout/db.sqlite. "
            "Clearing wipes persisted scans; the next `frontier-scout` launch "
            "re-runs a fresh dry-run scout, so this is safe to use.[/]"
        )

    def _automation_text(self) -> str:
        try:
            from frontier_scout.scheduling import (
                cron_runner_path,
                crontab_line,
                load_schedules,
            )
        except ImportError:
            return "[#e3c26f]scheduling module not importable on this install[/]"

        schedules = load_schedules()
        runner = cron_runner_path()
        lines = []
        if not schedules:
            lines.append(
                "[#6e8aa1]No schedules registered yet — quit, then run "
                "`frontier-scout setup` and pick Automation to add one.[/]"
            )
        else:
            for sched in schedules:
                state = "disabled" if sched.disabled else "active"
                last = sched.last_run or "never"
                lines.append(
                    f"[#d9f7ff bold]{Path(sched.repo).name}[/] · "
                    f"[#6e8aa1]{sched.cron_expr}[/] · "
                    f"[#6e8aa1]{state}[/] · "
                    f"[#6e8aa1]last: {last}[/]"
                )
        lines.append("")
        if runner.exists():
            lines.append("[#24d6a8]cron-runner.sh installed.[/] Add this once to your crontab:")
            lines.append(f"  [#d9f7ff]{crontab_line()}[/]")
        else:
            lines.append("[#e3c26f]cron-runner.sh not installed yet — wizard installs it.[/]")
        return "\n".join(lines)

    def _policy_text(self) -> str:
        try:
            candidates = [
                home_dir() / "policy.toml",
                Path(self.app_ref.diagnostics.repo) / ".frontier-scout" / "policy.toml",
            ]
        except Exception:  # noqa: BLE001
            return "[#e3c26f]policy paths unresolvable[/]"
        existing = []
        for p in candidates:
            try:
                if p.exists():
                    existing.append(p)
            except OSError:
                continue
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
            try:
                present = bool(os.environ.get(var))
            except Exception:  # noqa: BLE001
                present = False
            dot = "[#24d6a8 bold]●[/]" if present else "[#6e8aa1]●[/]"
            state = "present" if present else "missing"
            rows.append(f"{dot}  [#d9f7ff]{var:<22}[/] [#6e8aa1]{state}[/]")
        rows.append("")
        rows.append("[#6e8aa1]Values are never read or shown; only presence is checked.[/]")
        return "\n".join(rows)

    def _system_text(self) -> str:
        try:
            state = read_setup_state()
        except Exception as exc:  # noqa: BLE001
            state = {"_read_error": str(exc)}
        state_pretty = json.dumps(state, indent=2, sort_keys=True, default=str) if state else "{}"
        try:
            home = home_dir()
        except Exception as exc:  # noqa: BLE001
            home = f"<error: {exc}>"
        return "\n".join(
            [
                f"[#6e8aa1]version:    [/] [#d9f7ff]frontier-scout {__version__}[/]",
                f"[#6e8aa1]home:       [/] [#d9f7ff]{home}[/]",
                f"[#6e8aa1]repo:       [/] [#d9f7ff]{self.app_ref.diagnostics.repo}[/]",
                "",
                "[#d9f7ff bold]setup_state.json[/]",
                state_pretty,
            ]
        )
