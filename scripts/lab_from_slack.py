#!/usr/bin/env python3
"""
Slack 🧪 click → GitHub Actions entry point.

Round 4: this script wrote a markdown TODO to `.scratch/labs/`. Round 7
upgrades it to actually run the lab via `scripts/lab_runner.py`: pull the
tool, generate a stack-shaped synthetic test, run it in a hermetic
subprocess (env={} + PATH + HOME only), interpret the output, post a
threaded reply on the verdict card.

The script signature is preserved so the `lab-from-slack` GitHub Actions
workflow inputs (TOOL, URL, USER) stay simple.

Usage: python lab_from_slack.py "<tool>" "<url>" "<slack-user>"
"""

from __future__ import annotations

import sys

import lab_runner


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: lab_from_slack.py <tool> <url> <user>")
        return 1
    tool, url, user = sys.argv[1], sys.argv[2], sys.argv[3]
    return lab_runner.run(tool=tool, url=url, user=user)


if __name__ == "__main__":
    sys.exit(main())
