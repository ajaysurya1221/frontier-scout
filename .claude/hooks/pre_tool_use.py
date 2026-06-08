#!/usr/bin/env python3
"""Frontier Scout PreToolUse hook (generated — do not edit). Decides allow/deny/ask
and writes an action receipt. Self-contained: imports only the sibling _fs_guard."""
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
        return 0  # never break the session on a malformed event
    here = Path(__file__).resolve().parent
    repo = Path(os.environ.get("CLAUDE_PROJECT_DIR") or here.parent.parent)
    try:
        policy = json.loads((repo / "frontier-scout.policy.json").read_text())
    except Exception:
        policy = {}  # fail-closed: an empty policy asks/denies everything non-trivial
    lock = {}
    lock_path = repo / "policy.lock.json"
    if lock_path.exists():
        try:
            lock = json.loads(lock_path.read_text())
        except Exception:
            lock = {}
    out = guard.handle_pre_tool_use(
        event, policy=policy, policy_hash=lock.get("policy_sha256", ""),
        repo=str(repo), version=lock.get("frontier_scout_version"),
    )
    print(json.dumps(out))
    return 0


sys.exit(main())
