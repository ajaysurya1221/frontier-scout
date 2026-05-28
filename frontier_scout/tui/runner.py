"""Entry points for the setup terminal UI — v1.2.

No splash, no welcome modal. If the resolved repo doesn't look like a
repo, the TUI opens with a repo picker on top so the user can choose
before scanning anything. Import scan is *not* run synchronously; the
Scout tab fires its own worker after mount.
"""

from __future__ import annotations

import json
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
    show_splash: bool = True,  # ignored — splash deleted in v1.2.
    initial_tab: str = DEFAULT_TAB,
    auto_scout: bool = True,
) -> int:
    """Run setup in JSON, plain, or Textual mode."""

    selected_packs = packs if packs is not None else read_setup_state().get("selected_packs", [])

    # In TUI mode we defer the import scan so the UI mounts fast (<1s).
    # In plain/JSON mode we run the scan synchronously because the
    # caller wants the data in the output.
    tui_mode = not (plain or json_output)
    scan_for_diagnostics = scan_imports if not tui_mode else False

    diagnostics = setup_diagnostics(
        repo,
        ollama_url=ollama_url,
        selected_packs=selected_packs,
        scan_imports=scan_for_diagnostics,
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

    safe_tab = initial_tab if initial_tab in TAB_SLUGS else DEFAULT_TAB
    from frontier_scout.tui.repo_picker import (
        UNIVERSAL_SCOUT_SENTINEL,
        RepoPickerScreen,
        looks_like_repo,
    )

    picker_needed = not looks_like_repo(Path(diagnostics.repo))
    app = SetupApp(diagnostics, initial_tab=safe_tab)
    if picker_needed:
        original_on_mount = app.on_mount

        def _picker_callback(value: str | None) -> None:
            # Stream J — three outcomes from the picker:
            #   * None      → user clicked Quit. Close the app cleanly.
            #   * sentinel  → user opted for universal scout. Mark the
            #                 app's universal_mode flag and update the
            #                 brand bar to reflect "not tailored".
            #   * any other → a resolved repo path. Hand it to the
            #                 standard refresh-diagnostics path.
            if value is None:
                app.exit()
                return
            if value == UNIVERSAL_SCOUT_SENTINEL:
                app.universal_mode = True
                app._set_status_banner(
                    "Universal scout — verdicts are NOT tailored to a specific repo.",
                    tone="warn",
                )
                # Trigger a fresh scout in universal mode.
                try:
                    from frontier_scout.tui.tabs.scout_tab import ScoutTab

                    scout_tab = app.query_one(ScoutTab)
                    scout_tab._scout_worker()
                except Exception:  # noqa: BLE001 — defensive
                    pass
                return
            app._handle_picker_choice(value)

        def patched_on_mount() -> None:
            original_on_mount()
            app.push_screen(RepoPickerScreen(), _picker_callback)

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
