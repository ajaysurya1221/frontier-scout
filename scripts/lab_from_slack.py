#!/usr/bin/env python3
"""
Slack reaction → lab queue.

When a teammate reacts 🧪 on a Slack post, Slack Workflow Builder triggers the
`lab-from-slack` custom pipeline. This script writes a markdown file under
.scratch/labs/ so the next operator has a concrete task to pick up.

The next person running the `lab <tool>` skill picks up the oldest open file.

Usage: python lab_from_slack.py "<tool>" "<url>" "<slack-user>"
"""

import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
QUEUE = REPO_ROOT / ".scratch" / "labs"


def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def main():
    if len(sys.argv) < 4:
        print("Usage: lab_from_slack.py <tool> <url> <user>")
        sys.exit(1)
    tool, url, user = sys.argv[1], sys.argv[2], sys.argv[3]
    today = datetime.now().strftime("%Y-%m-%d")
    QUEUE.mkdir(parents=True, exist_ok=True)
    path = QUEUE / f"{today}-{slug(tool)}.md"
    path.write_text(
        f"# Lab: {tool}\n\n"
        f"_Queued by @{user} via 🧪 reaction on {today}._\n\n"
        f"Source: {url}\n\n"
        f"## Action\n"
        f"Run the `lab` skill on `{tool}` and report findings to `skills-log.md`.\n"
        f"Delete this file when done.\n"
    )
    print(f"✓ Queued lab → {path}")


if __name__ == "__main__":
    main()
