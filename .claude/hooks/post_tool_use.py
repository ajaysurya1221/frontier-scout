#!/usr/bin/env python3
"""Frontier Scout PostToolUse hook (generated — do not edit). Records the realized
outcome of a completed tool call as an action receipt."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _fs_guard as guard  # noqa: E402


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    here = Path(__file__).resolve().parent
    repo = Path(os.environ.get("CLAUDE_PROJECT_DIR") or here.parent.parent)
    lock = {}
    lock_path = repo / "policy.lock.json"
    if lock_path.exists():
        try:
            lock = json.loads(lock_path.read_text())
        except Exception:
            lock = {}
    guard.handle_post_tool_use(
        event, policy_hash=lock.get("policy_sha256", ""),
        repo=str(repo), version=lock.get("frontier_scout_version"),
    )
    return 0


sys.exit(main())
