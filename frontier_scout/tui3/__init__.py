"""Mission Control — the dense, tabbed Frontier Scout TUI (tui3).

Implements the "Frontier Scout Mission Control" design: a responsive,
keyboard-first dashboard with eight capability tabs (Scout, Schedule, Receipts,
Guard, Packs, Deps, Reports, Settings), each wired to real Frontier Scout
backends. Renders flawlessly from 36×11 up to 200+ columns, with unicode/ASCII
and color/mono fallbacks.

``run_mission_control`` is the entry point; the CLI selects it as the default UI
(``--ui briefing`` → tui2, ``--ui classic`` → tui).
"""

from __future__ import annotations

from pathlib import Path


def run_mission_control(*, repo: Path | None = None, demo: bool = False) -> int:
    """Launch the Mission Control app. Imported lazily to keep CLI start fast."""
    from frontier_scout.tui3.app import MissionControlApp

    return MissionControlApp(repo=repo, demo=demo).run()


__all__ = ["run_mission_control"]
