"""Entry points for the setup terminal UI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from frontier_scout.store import read_setup_state
from frontier_scout.tui.setup_diagnostics import diagnostics_to_plain, setup_diagnostics
from frontier_scout.tui.tabs import DEFAULT_TAB, TAB_SLUGS


def run_setup(
    *,
    repo: Path,
    plain: bool = False,
    json_output: bool = False,
    ollama_url: str = "http://localhost:11434",
    packs: list[str] | None = None,
    scan_imports: bool = True,
    show_splash: bool = True,
    initial_tab: str = DEFAULT_TAB,
    auto_scout: bool = True,
) -> int:
    """Run setup in JSON, plain, or Textual mode."""

    selected_packs = packs if packs is not None else read_setup_state().get("selected_packs", [])
    diagnostics = setup_diagnostics(
        repo,
        ollama_url=ollama_url,
        selected_packs=selected_packs,
        scan_imports=scan_imports,
    )
    if json_output:
        payload = diagnostics.model_dump()
        payload["tabs"] = TAB_SLUGS
        payload["verdicts"] = _scout_verdicts(repo) if auto_scout else []
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
        output = diagnostics_to_plain(diagnostics)
        if auto_scout:
            output += _scout_plain_section(repo)
        print(output, end="")
        return 0
    try:
        from frontier_scout.tui.setup_app import SetupApp
    except ImportError as exc:
        print("Textual setup UI is unavailable; falling back to plain setup.")
        print(f"reason: {exc}")
        print()
        print(diagnostics_to_plain(diagnostics), end="")
        return 0
    splash_env = os.environ.get("FRONTIER_SCOUT_SKIP_SPLASH", "")
    effective_splash = show_splash and splash_env.lower() not in ("1", "true", "yes")
    safe_tab = initial_tab if initial_tab in TAB_SLUGS else DEFAULT_TAB

    # If the resolved repo doesn't look like a real repo, swap it for the
    # user's $HOME so the TUI has something to fingerprint, then push a
    # picker on top so they can choose. ``looks_like_repo`` is conservative.
    from frontier_scout.tui.repo_picker import RepoPickerScreen, looks_like_repo

    picker_needed = not looks_like_repo(Path(diagnostics.repo))
    app = SetupApp(diagnostics, show_splash=effective_splash, initial_tab=safe_tab)
    if picker_needed:
        def _on_picked(value: str | None) -> None:
            if value:
                app._handle_picker_choice(value)  # type: ignore[attr-defined]

        original_on_mount = app.on_mount

        def patched_on_mount() -> None:
            original_on_mount()
            app.push_screen(RepoPickerScreen(), _on_picked)

        app.on_mount = patched_on_mount  # type: ignore[method-assign]
    app.run()
    return 0


def _scout_verdicts(repo: Path) -> list[dict]:
    """Run a quick dry-run scout so --json includes verdicts."""
    try:
        from frontier_scout.scout import run_scan

        payload = run_scan(repo=repo, dry_run=True, persist=False)
        return list(payload.get("verdicts") or [])
    except Exception:
        return []


def _scout_plain_section(repo: Path) -> str:
    verdicts = _scout_verdicts(repo)
    lines = ["", "Scout (latest AI releases that fit this repo)"]
    if not verdicts:
        lines.append("- no verdicts (run `frontier-scout scan --dry-run` for the live CLI surface)")
        return "\n".join(lines) + "\n"
    for v in verdicts:
        verdict = str(v.get("verdict", "—")).upper()
        lines.append(
            f"- {verdict:<7} {v.get('tool_name', '—')}  "
            f"fit={v.get('fit', '—')} risk={v.get('risk', '—')} "
            f"({v.get('category', '—')})"
        )
    return "\n".join(lines) + "\n"
