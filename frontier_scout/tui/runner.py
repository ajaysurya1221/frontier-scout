"""Entry points for the setup terminal UI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import diagnostics_to_plain, setup_diagnostics


def run_setup(
    *,
    repo: Path,
    plain: bool = False,
    json_output: bool = False,
    ollama_url: str = "http://localhost:11434",
) -> int:
    """Run setup in JSON, plain, or Textual mode."""

    diagnostics = setup_diagnostics(repo, ollama_url=ollama_url)
    if json_output:
        print(json.dumps(diagnostics.model_dump(), indent=2))
        return 0
    if plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(diagnostics_to_plain(diagnostics), end="")
        return 0
    try:
        from frontier_scout.tui.setup_app import SetupApp
    except ImportError as exc:
        print("Textual setup UI is unavailable; falling back to plain setup.")
        print(f"reason: {exc}")
        print()
        print(diagnostics_to_plain(diagnostics), end="")
        return 0
    app = SetupApp(diagnostics)
    app.run()
    return 0

