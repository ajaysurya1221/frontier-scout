"""CLI wrapper for the polyglot lab runner."""

from __future__ import annotations

import sys
from pathlib import Path


def run_lab(tool: str, url: str, *, dry_run: bool = False) -> int:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from lab_runner import run  # type: ignore

    return int(run(tool=tool, url=url, user="", dry_run=dry_run))

