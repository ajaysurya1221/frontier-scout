"""Textual setup wizard — runs as a standalone App.

Four screens (Welcome → LLM → Mode → Automation|Ad-hoc), each with the
designer's mint palette. Persists choices and offers an
[Open Mission Control] button at the end.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from frontier_scout import __version__
from frontier_scout.scheduling import (
    add_schedule,
    crontab_line,
    install_cron_runner,
    is_valid_cron_expr,
    load_schedules,
)
from frontier_scout.tui.setup_diagnostics import detect_providers
from frontier_scout.wizard.config import (
    mark_wizard_complete,
    update_llm,
    update_mode,
)

_WIZARD_CSS = """
Screen {
    background: #0b1117;
    color: #d9f7ff;
    align: center middle;
}

#wizard-frame {
    width: 84;
    height: auto;
    padding: 1 3;
    border: round #24d6a8;
    background: #0d1622;
}

#wizard-step {
    color: #6e8aa1;
}

#wizard-title {
    text-style: bold;
    color: #d9f7ff;
    margin-bottom: 1;
}

#wizard-body {
    color: #d9f7ff;
    margin-bottom: 1;
}

.wizard-card {
    border: round #25405c;
    padding: 1 2;
    margin-bottom: 1;
    background: #08131d;
}

.wizard-card.selected {
    border: round #24d6a8;
    background: #0d2520;
}

.wizard-card-title {
    text-style: bold;
    color: #d9f7ff;
}

.wizard-card-detail {
    color: #6e8aa1;
}

.wizard-controls {
    height: 3;
    align-horizontal: right;
}

Button {
    margin-left: 1;
    background: #0d1622;
    color: #d9f7ff;
    border: round #25405c;
}

Button:focus {
    border: round #24d6a8;
    color: #24d6a8;
}

Input {
    margin-top: 1;
    border: round #25405c;
}

Input:focus {
    border: round #7aa6ff;
}
"""


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


class WelcomeScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("step 1 of 4", id="wizard-step")
            yield Static(f"◉ FRONTIER · SCOUT · setup · v{__version__}", id="wizard-title")
            yield Static(
                "[#d9f7ff]The radar for latest AI releases that fit your repo.[/]\n\n"
                "This wizard configures your machine once. You can re-run it anytime.\n\n"
                "[#24d6a8]Safety contract:[/]\n"
                "  · Local-first. Your repo content is never sent to an LLM.\n"
                "  · No tools installed by us. No services logged into.\n"
                "  · API keys are never written to disk by Frontier Scout.\n\n"
                "[#6e8aa1]Press Enter to continue, or Esc to skip the wizard.[/]",
                id="wizard-body",
                markup=True,
            )
            with Horizontal(classes="wizard-controls"):
                yield Button("Skip wizard", id="wiz-welcome-skip")
                yield Button("Continue →", id="wiz-welcome-continue")


class LLMStepScreen(Screen[None]):
    BINDINGS: ClassVar = [Binding("escape", "back", "Back", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("step 2 of 4", id="wizard-step")
            yield Static("Choose a model backend", id="wizard-title")
            yield Static(
                "[#6e8aa1]Frontier Scout works fully offline with the Local deterministic backend. "
                "Add an LLM only when you want live verdicts, evaluations, or trial judgments.[/]",
                id="wizard-body",
                markup=True,
            )
            with VerticalScroll():
                for backend, title, body, hint in _backend_cards():
                    with Vertical(classes="wizard-card", id=f"backend-{backend}"):
                        yield Label(title, classes="wizard-card-title")
                        yield Static(body, classes="wizard-card-detail", markup=True)
                        if hint:
                            yield Static(f"[#e3c26f]{hint}[/]", classes="wizard-card-detail", markup=True)
                        yield Button(f"Pick {backend}", id=f"pick-{backend}")
            with Horizontal(classes="wizard-controls"):
                yield Button("← Back", id="wiz-llm-back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("pick-"):
            backend = event.button.id.removeprefix("pick-")
            update_llm(backend)
            self.app.push_screen(ModeStepScreen())
        elif event.button.id == "wiz-llm-back":
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class ModeStepScreen(Screen[None]):
    BINDINGS: ClassVar = [Binding("escape", "back", "Back", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("step 3 of 4", id="wizard-step")
            yield Static("How do you want to use Frontier Scout?", id="wizard-title")
            with Vertical(classes="wizard-card"):
                yield Label("Automation", classes="wizard-card-title")
                yield Static(
                    "[#6e8aa1]Schedule recurring scouts for your repos. Best for teams "
                    "who want to know about new releases without lifting a finger.[/]",
                    classes="wizard-card-detail",
                    markup=True,
                )
                yield Button("Set up automation", id="mode-automation")
            with Vertical(classes="wizard-card"):
                yield Label("Ad-hoc", classes="wizard-card-title")
                yield Static(
                    "[#6e8aa1]Run scouts manually whenever you want. Best for exploring. "
                    "Just type `frontier-scout` inside any repo.[/]",
                    classes="wizard-card-detail",
                    markup=True,
                )
                yield Button("Stay ad-hoc", id="mode-adhoc")
            with Horizontal(classes="wizard-controls"):
                yield Button("← Back", id="wiz-mode-back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mode-automation":
            update_mode("automation")
            self.app.push_screen(AutomationStepScreen())
        elif event.button.id == "mode-adhoc":
            update_mode("adhoc")
            mark_wizard_complete()
            self.app.push_screen(AdhocStepScreen())
        elif event.button.id == "wiz-mode-back":
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()


class AutomationStepScreen(Screen[None]):
    BINDINGS: ClassVar = [Binding("escape", "back", "Back", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("step 4 of 4 · automation", id="wizard-step")
            yield Static("Schedule recurring scouts", id="wizard-title")
            yield Static(
                "[#6e8aa1]Add one repo per line. Use absolute paths.[/]",
                markup=True,
            )
            yield Input(placeholder="/path/to/repo", id="auto-repo")
            yield Static("Cron expression (or @daily / @weekly / @hourly):")
            yield Input(value="@daily", id="auto-cron")
            yield Static(
                "[#6e8aa1]Notification: file (always written) — system notification fires only "
                "if `terminal-notifier` (macOS) or `notify-send` (Linux) is on PATH.[/]",
                markup=True,
            )
            yield Static("", id="auto-status", markup=True)
            with Horizontal(classes="wizard-controls"):
                yield Button("← Back", id="wiz-auto-back")
                yield Button("Install schedule", id="auto-install")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "wiz-auto-back":
            self.app.pop_screen()
            return
        if event.button.id != "auto-install":
            return
        repo_raw = self.query_one("#auto-repo", Input).value.strip()
        cron_raw = self.query_one("#auto-cron", Input).value.strip() or "@daily"
        status = self.query_one("#auto-status", Static)
        if not repo_raw:
            status.update("[#ff6b6b]Enter at least one repo path.[/]")
            return
        repo_path = Path(repo_raw).expanduser()
        try:
            resolved = repo_path.resolve()
        except OSError:
            status.update(f"[#ff6b6b]Invalid path: {repo_raw}[/]")
            return
        if not resolved.exists() or not resolved.is_dir():
            status.update(f"[#ff6b6b]Not a directory: {resolved}[/]")
            return
        if not is_valid_cron_expr(cron_raw):
            status.update(f"[#ff6b6b]Invalid cron expression: {cron_raw}[/]")
            return
        runner = install_cron_runner()
        sched = add_schedule(resolved, cron_expr=cron_raw, notification="file")
        line = crontab_line()
        mark_wizard_complete()
        body = (
            f"[#24d6a8 bold]Schedule installed.[/]\n\n"
            f"[#d9f7ff]Runner:[/] {runner}\n"
            f"[#d9f7ff]Schedules ({len(load_schedules())}):[/] {sched.repo} @ {sched.cron_expr}\n\n"
            f"[#e3c26f]One more step.[/] Add this single line to your crontab "
            f"(`crontab -e`), then save:\n\n"
            f"  [#d9f7ff bold]{line}[/]\n\n"
            f"After that, every schedule you ever add runs automatically.\n\n"
            f"[#6e8aa1]Press Enter to finish.[/]"
        )
        self.app.push_screen(_DoneScreen(message=body))

    def action_back(self) -> None:
        self.app.pop_screen()


class AdhocStepScreen(Screen[None]):
    BINDINGS: ClassVar = [Binding("escape", "exit", "Exit", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("step 4 of 4 · ad-hoc", id="wizard-step")
            yield Static("You're set up", id="wizard-title")
            yield Static(
                "[#d9f7ff]Frontier Scout stays out of the way until you call it. "
                "From any repo:[/]\n\n"
                "  [#24d6a8 bold]cd ~/Desktop/my-repo[/]\n"
                "  [#24d6a8 bold]frontier-scout[/]\n\n"
                "That opens Mission Control. Inside the TUI:\n"
                "  · [#d9f7ff]1 — 2[/] switch between Scout and Settings\n"
                "  · [#d9f7ff]?[/] shows the full keymap\n"
                "  · [#d9f7ff]q[/] quits with a confirmation\n\n"
                "[#6e8aa1]Tip:[/] run [#d9f7ff]`frontier-scout setup`[/] anytime to switch to "
                "automation mode, change your LLM backend, or wipe scout history.\n\n"
                "[#6e8aa1]Press Esc to exit, or open Mission Control now.[/]",
                markup=True,
            )
            with Horizontal(classes="wizard-controls"):
                yield Button("Exit (Esc)", id="adhoc-exit")
                yield Button("Open Mission Control now", id="adhoc-open")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "adhoc-exit":
            self.app.exit()
        elif event.button.id == "adhoc-open":
            self.app.exit(result="open-tui")

    def action_exit(self) -> None:
        self.app.exit()


class _DoneScreen(Screen[None]):
    BINDINGS: ClassVar = [
        Binding("enter", "finish", "Finish", show=False),
        Binding("escape", "finish", "Finish", show=False),
    ]

    def __init__(self, *, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-frame"):
            yield Static("done", id="wizard-step")
            yield Static("Setup complete", id="wizard-title")
            yield Static(self._message, markup=True)
            with Horizontal(classes="wizard-controls"):
                yield Button("Copy crontab line", id="copy-cron")
                yield Button("Open Mission Control now", id="done-open")
                yield Button("Quit", id="done-quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-cron":
            self._copy_to_clipboard(crontab_line())
        elif event.button.id == "done-open":
            self.app.exit(result="open-tui")
        elif event.button.id == "done-quit":
            self.app.exit()

    def action_finish(self) -> None:
        self.app.exit()

    def _copy_to_clipboard(self, text: str) -> None:
        for cmd in ("pbcopy", "wl-copy", "xclip"):
            if not shutil.which(cmd):
                continue
            try:
                if cmd == "xclip":
                    args = [cmd, "-selection", "clipboard"]
                else:
                    args = [cmd]
                subprocess.run(args, input=text.encode(), check=False, timeout=2)
                return
            except (OSError, subprocess.TimeoutExpired):
                continue
        # Best-effort only — no clipboard tool found.


# ---------------------------------------------------------------------------
# Backend cards
# ---------------------------------------------------------------------------


def _backend_cards() -> list[tuple[str, str, str, str]]:
    """Return (id, title, body, hint) tuples for each backend card."""

    providers = detect_providers(ollama_timeout_s=0.25)
    by_name = {p.name: p for p in providers}
    cards: list[tuple[str, str, str, str]] = []
    # Local deterministic — always available.
    cards.append(
        (
            "local",
            "Local deterministic · available",
            "[#24d6a8]Recommended for first runs.[/] No AI, no API spend. "
            "Verdicts come from seeded data; perfect for demos and exploring.",
            "",
        )
    )
    ollama = by_name.get("Ollama")
    if ollama and ollama.status == "found":
        models = ", ".join(ollama.models[:3]) or "no models listed"
        cards.append(
            (
                "ollama",
                f"Ollama · found ({models})",
                "Local model runtime. Lives entirely on your machine. "
                "Frontier Scout will use whatever models you have pulled.",
                "",
            )
        )
    else:
        cards.append(
            (
                "ollama",
                "Ollama · not reachable",
                "Local model runtime. Best balance of cost (free) and quality.",
                "Setup: `brew install ollama && ollama pull qwen3:4b`, then re-run this wizard.",
            )
        )
    for name, env_var, key in (
        ("Anthropic API", "ANTHROPIC_API_KEY", "anthropic_api"),
        ("OpenAI API", "OPENAI_API_KEY", "openai_api"),
    ):
        provider = by_name.get(name)
        if provider and provider.status == "present":
            cards.append(
                (
                    key,
                    f"{name} · key present",
                    "Live judgments + evaluations. Costs ~$0.30/scan; the offline radar is free.",
                    "",
                )
            )
        else:
            cards.append(
                (
                    key,
                    f"{name} · key not set",
                    "Live judgments + evaluations. Costs ~$0.30/scan.",
                    f"Setup: `export {env_var}=sk-...` in your shell init, then re-run this wizard.",
                )
            )
    return cards


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class WizardApp(App[str]):
    """The wizard. Returns 'open-tui' if the user wants Mission Control next."""

    CSS = _WIZARD_CSS
    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit", show=False),
        Binding("escape", "back_or_quit", "Back / Quit", show=False),
    ]

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Welcome screen handler routes here too.
        if event.button.id == "wiz-welcome-skip":
            self.exit()
        elif event.button.id == "wiz-welcome-continue":
            self.push_screen(LLMStepScreen())

    def action_quit(self) -> None:
        self.exit()

    def action_back_or_quit(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
        else:
            self.exit()
