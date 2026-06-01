"""BriefingApp — the controller that owns the single AppState and all flows.

Every async flow follows the same total-function shape: push WorkingScreen,
run a thread worker that emits Progress events and exactly one terminal message
(WorkDone/WorkFailed), then land on a result or error screen. The app holds an
immutable :class:`AppState`; screens read from it and never write to each other.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App
from textual.binding import Binding

from frontier_scout.tui2.messages import Progress, WorkDone, WorkFailed
from frontier_scout.tui2.reporter import TuiReporter
from frontier_scout.tui2.screens.action_result import ActionResultScreen
from frontier_scout.tui2.screens.error import ErrorScreen
from frontier_scout.tui2.screens.findings import FindingsScreen
from frontier_scout.tui2.screens.home import HomeScreen
from frontier_scout.tui2.screens.working import WorkingScreen
from frontier_scout.tui2.state import AppState, Finding


class BriefingApp(App):
    CSS_PATH = "theme.tcss"
    TITLE = "frontier · scout"
    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False, priority=True),
    ]

    def __init__(
        self, *, repo: Path | None = None, demo: bool = False, splash: bool = False
    ) -> None:
        super().__init__()
        repo = (repo or Path.cwd()).resolve()
        has_repo = _looks_like_repo(repo)
        try:
            from frontier_scout.store import read_setup_state

            dismissed = frozenset(read_setup_state().get("dismissed_tools") or [])
        except Exception:  # noqa: BLE001
            dismissed = frozenset()
        self.state = AppState(
            repo=str(repo),
            repo_name=repo.name,
            has_repo=has_repo,
            dismissed=dismissed,
        )
        self._demo = demo
        self._splash = splash
        self._gen = 0

    def on_mount(self) -> None:
        if self._splash:
            from frontier_scout.tui2.screens.splash import SplashScreen

            self.push_screen(SplashScreen())
        else:
            self.push_screen(HomeScreen())

    def provider_label(self) -> str:
        """A short, friendly label for the active backend (for the home kicker)."""
        if self._demo or not _has_provider():
            return "offline demo"
        try:
            from frontier_scout.providers import available_providers

            names = available_providers()
            return names[0] if names else "offline demo"
        except Exception:  # noqa: BLE001
            return "offline demo"

    # ── Worker bridge ───────────────────────────────────────────────────────

    def _launch(self, kind: str, title: str, fn: Callable[[TuiReporter], Any]) -> None:
        self._gen += 1
        gen = self._gen
        self.push_screen(WorkingScreen(title))
        self._run_worker(kind, gen, fn)

    @work(thread=True)
    def _run_worker(self, kind: str, gen: int, fn: Callable[[TuiReporter], Any]) -> None:
        reporter = TuiReporter(self)
        try:
            payload = fn(reporter)
        except Exception as exc:  # noqa: BLE001 — errors become a screen, never a crash
            if gen == self._gen:
                self.post_message(WorkFailed(kind, _humanise(exc)))
            return
        if gen == self._gen:
            self.post_message(WorkDone(kind, payload))

    def on_progress(self, message: Progress) -> None:
        if isinstance(self.screen, WorkingScreen):
            self.screen.apply_progress(message)

    def on_work_done(self, message: WorkDone) -> None:
        if not isinstance(self.screen, WorkingScreen):
            return  # cancelled or superseded; ignore late completion
        if message.kind in ("scout", "explore"):
            findings: tuple[Finding, ...] = message.payload
            self.state = self.state.with_(findings=findings, cursor=0)
            self._finish(FindingsScreen())
        elif message.kind == "implement":
            self._finish(ActionResultScreen("implement", message.payload))
        else:
            self._finish(ActionResultScreen("text", message.payload))

    def on_work_failed(self, message: WorkFailed) -> None:
        if not isinstance(self.screen, WorkingScreen):
            return
        self._finish(ErrorScreen(message.error, message.suggestion))

    def _finish(self, screen: Any) -> None:
        if isinstance(self.screen, WorkingScreen):
            self.pop_screen()
        self.push_screen(screen)

    def cancel_work(self) -> None:
        self._gen += 1  # suppress any in-flight worker's terminal message
        if isinstance(self.screen, WorkingScreen):
            self.pop_screen()

    # ── Flow launchers ───────────────────────────────────────────────────────

    def start_scout(self) -> None:
        repo = Path(self.state.repo or ".")
        demo = self._demo or not _has_provider()

        def fn(reporter: TuiReporter) -> tuple[Finding, ...]:
            from frontier_scout.scout import run_scan

            payload = run_scan(repo=repo, dry_run=demo, persist=not demo, reporter=reporter)
            verdicts = payload.get("verdicts") or []
            return tuple(Finding.from_verdict(v) for v in verdicts)

        self._launch("scout", f"Scouting {self.state.repo_name}…", fn)

    def start_explore(self, query: str) -> None:
        def fn(reporter: TuiReporter) -> tuple[Finding, ...]:
            from frontier_scout.evaluate import evaluate_url

            ev = evaluate_url(query, reporter=reporter)
            return (_finding_from_evaluation(ev),)

        self._launch("explore", f"Exploring {query}…", fn)

    def start_implement(self, finding: Finding) -> None:
        repo = Path(self.state.repo or ".")

        def fn(reporter: TuiReporter) -> Any:
            from frontier_scout.implement import run_implement

            return run_implement(repo=repo, tool_name=finding.tool_name, reporter=reporter)

        self._launch("implement", f"Implementing {finding.tool_name}…", fn)

    def start_explain(self, finding: Finding) -> None:
        """Deeper deterministic read (fit + security) — offline, no spend."""
        from frontier_scout.evaluate import evaluate_url

        try:
            ev = evaluate_url(finding.url or finding.tool_name)
            text = _explain_text(ev)
        except Exception as exc:  # noqa: BLE001
            self.push_screen(ErrorScreen(_humanise(exc)))
            return
        self.push_screen(ActionResultScreen("text", (f"Tell me more · {finding.tool_name}", text)))

    def start_lab(self, finding: Finding) -> None:
        """Show the exact hermetic-lab command (no in-process install/spend)."""
        url = finding.url or "<repo-url>"
        text = (
            "A lab installs the tool in a throwaway sandbox and runs a probe so "
            "you get evidence before adopting — nothing touches your machine.\n\n"
            "[b]Run it from your shell[/b]\n"
            f"  frontier-scout lab {finding.tool_name} --url {url} --progress\n\n"
            "[dim]Kept out of the TUI on purpose: real installs belong in your "
            "own shell where you can see every command.[/dim]"
        )
        self.push_screen(ActionResultScreen("text", (f"Lab · {finding.tool_name}", text)))

    # ── Card / settings side-effects ─────────────────────────────────────────

    def dismiss_finding(self, tool_name: str) -> None:
        self.state = self.state.with_(dismissed=self.state.dismissed | {tool_name})
        try:
            from frontier_scout.store import read_setup_state, write_setup_state

            st = read_setup_state()
            dismissed = list(st.get("dismissed_tools") or [])
            if tool_name not in dismissed:
                dismissed.append(tool_name)
                st["dismissed_tools"] = dismissed
                write_setup_state(st)
        except Exception:  # noqa: BLE001
            pass

    def keep_implement(self, result: Any) -> None:
        try:
            from frontier_scout.implement import keep_changes

            keep_changes(result)
        except Exception:  # noqa: BLE001
            pass

    def discard_implement(self, result: Any) -> None:
        try:
            from frontier_scout.implement import discard

            discard(result)
        except Exception:  # noqa: BLE001
            pass

    def run_settings_action(self, key: str) -> str:
        try:
            from frontier_scout import store

            if key == "clear_repo":
                n = store.clear_scans_for_repo(self.state.repo)
                return f"Cleared memory for this repo ({n} scan(s))."
            if key == "clear_all":
                n = store.clear_all_scans()
                return f"Cleared all memory ({n} scan(s))."
        except Exception as exc:  # noqa: BLE001
            return f"Could not clear: {_humanise(exc)}"
        return "Nothing to do."


# ── Pure helpers ─────────────────────────────────────────────────────────────


def _looks_like_repo(path: Path) -> bool:
    markers = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "setup.py")
    return any((path / m).exists() for m in markers)


def _has_provider() -> bool:
    try:
        from frontier_scout.providers import available_providers

        return bool(available_providers())
    except Exception:  # noqa: BLE001
        return False


def _humanise(exc: Exception) -> str:
    msg = str(exc).strip()
    name = type(exc).__name__
    if "ProviderUnavailable" in name or "provider" in msg.lower():
        return msg or "No LLM provider configured — run `frontier-scout setup`."
    return msg or name


def _finding_from_evaluation(ev: Any) -> Finding:
    bits = [ev.category, f"trust {ev.source_trust}", f"score {ev.score}/10"]
    summary = " · ".join(b for b in bits if b)
    if getattr(ev, "evidence", None):
        summary += "\n" + "; ".join(str(e) for e in ev.evidence)
    return Finding(
        tool_name=ev.tool_name,
        verdict="assess",
        fit=str(ev.fit),
        risk=str(ev.risk),
        category=str(ev.category),
        summary=summary,
        why_fit="",
        next_step=f"frontier-scout lab {ev.tool_name} --url {ev.source_url}",
        url=str(ev.source_url),
    )


def _explain_text(ev: Any) -> str:
    lines = [
        f"[b]Fit[/b] {ev.fit}    [b]Risk[/b] {ev.risk}    [b]Category[/b] {ev.category}",
        f"[b]Source trust[/b] {ev.source_trust}    [b]Score[/b] {ev.score}/10",
    ]
    manifest = getattr(ev, "permission_manifest", None)
    flags = getattr(manifest, "dangerous_flags", None) if manifest else None
    if flags:
        lines.append("[b]Permission surface[/b]\n  " + ", ".join(flags))
    else:
        lines.append("[b]Permission surface[/b]\n  no dangerous capabilities detected")
    if getattr(ev, "evidence", None):
        lines.append("[b]Evidence[/b]\n  " + "\n  ".join(str(e) for e in ev.evidence))
    return "\n\n".join(lines)


def run_briefing(*, repo: Path | None = None, demo: bool = False) -> int:
    """Run the Briefing TUI. Returns a process exit code."""
    os.environ.setdefault("TEXTUAL_ANIMATIONS", "none")
    app = BriefingApp(repo=repo, demo=demo, splash=True)
    app.run()
    return 0
