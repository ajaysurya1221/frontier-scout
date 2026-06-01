#!/usr/bin/env python3
"""Generate the offline Frontier Scout demo report.

This script is kept for source-checkout convenience. The packaged entry point
is `frontier-scout demo`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontier_scout.report import SAMPLE_DATE, SAMPLE_FUNNEL, SAMPLE_VERDICTS, write_demo

# SAMPLE_DATE / SAMPLE_FUNNEL / SAMPLE_VERDICTS are re-exported (not used in this
# module): ``scripts/scout.py``'s dry-run path does ``from demo import
# SAMPLE_VERDICTS``. Declaring __all__ keeps them in the public surface so
# ruff's F401 autofix never strips them as "unused imports".
__all__ = ["SAMPLE_DATE", "SAMPLE_FUNNEL", "SAMPLE_VERDICTS", "main", "write_demo"]


REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "demo"


def main() -> int:
    paths = write_demo(DEMO_DIR)
    print(f"Wrote HTML report: {paths['html']}")
    print(f"Wrote Markdown briefing: {paths['markdown']}")
    print(f"Wrote verdict data: {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
