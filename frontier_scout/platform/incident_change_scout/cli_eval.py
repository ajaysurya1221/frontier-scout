"""Command-line eval runner for the Incident Change Scout demo."""

from __future__ import annotations

import json
from pathlib import Path

from .workflow import run_incident_demo


def main() -> int:
    summary = run_incident_demo(
        corpus_dir=Path("examples/incident_change_scout/corpus"),
        ticket_path=Path("examples/incident_change_scout/tickets/cache-storm.md"),
        output_dir=Path(".scratch/incident-eval"),
    )
    print(json.dumps(summary["eval"], indent=2))
    return 0 if summary["eval"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
