"""Compile an :class:`AgentPolicy` into Claude Code native controls + a CI verifier.

Frontier Scout **emits** native config; Claude Code and GitHub Actions **enforce** it.
Nothing here runs an agent, a tool, or an MCP server.

Artifacts written (under ``out_dir``, with the policy + lock at ``repo`` root):
  * ``frontier-scout.policy.json``  — the exact compiled policy (so hook == lock)
  * ``policy.lock.json``            — sha256 binding receipts to this policy
  * ``.claude/settings.json``       — permissions (allow/deny/ask) + hook wiring
  * ``.claude/hooks/_fs_guard.py``  — verbatim copy of the stdlib hook runtime
  * ``.claude/hooks/pre_tool_use.py`` / ``post_tool_use.py`` — thin entrypoints
  * ``managed-settings.json``       — admin/MDM allow/deny MCP fragment
  * ``.github/workflows/frontier-scout-verify.yml`` — the PR verifier workflow
"""

from __future__ import annotations

import json
from pathlib import Path

from outputs._text import sanitize_sensitive_text

from ..exporters.claude_config import to_managed_config_from_names
from . import hook_runtime
from .lock import write_lock
from .models import AgentPolicy
from .policy import save_policy

__all__ = ["compile_claude", "build_permissions", "build_settings"]

_PRE_HOOK = '''#!/usr/bin/env python3
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
'''

_POST_HOOK = '''#!/usr/bin/env python3
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
'''

_WORKFLOW = """# Frontier Scout — verify PR stayed within approved scope (generated).
name: Frontier Scout verify
on:
  pull_request:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install frontier-scout
      - run: >-
          frontier-scout agent verify-pr --repo .
          --base "origin/${{ github.base_ref }}"
          --receipts "frontier-scout-receipts/*.json"
"""


def build_permissions(policy: AgentPolicy) -> dict[str, list[str]]:
    """Translate the policy into a Claude ``permissions`` block (deny > ask > allow)."""

    deny: list[str] = [f"Bash({c}:*)" for c in policy.blocked_shell_commands if c]
    deny += [t for t in policy.blocked_tools if t]

    ask: list[str] = []
    for glob in policy.protected_file_globs:
        ask += [f"Edit({glob})", f"Write({glob})"]
    if "network" in policy.approval_gates:
        ask.append("WebFetch")

    allow: list[str] = [f"Bash({c}:*)" for c in policy.allowed_shell_commands if c]
    for glob in policy.allowed_file_globs:
        allow += [f"Edit({glob})", f"Write({glob})"]
    allow += [f"mcp__{s}__*" for s in policy.mcp_server_allowlist if s]
    allow += [t for t in policy.allowed_tools if t]

    # de-dup while preserving order
    return {
        "allow": list(dict.fromkeys(allow)),
        "deny": list(dict.fromkeys(deny)),
        "ask": list(dict.fromkeys(ask)),
    }


def build_settings(policy: AgentPolicy) -> dict:
    """Build the full ``.claude/settings.json`` payload (permissions + hooks)."""

    def _cmd(name: str) -> str:
        return f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{name}"'

    return {
        "permissions": build_permissions(policy),
        "hooks": {
            event: [{"matcher": "*", "hooks": [{"type": "command", "command": _cmd(script)}]}]
            for event, script in (
                ("PreToolUse", "pre_tool_use.py"),
                ("PostToolUse", "post_tool_use.py"),
            )
        },
    }


def _write_verbatim(path: Path, text: str) -> str:
    """Trusted code/config written byte-for-byte (the guard must equal the tested
    runtime; redacting it would mangle its own secret-pattern regexes)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def _write_config(path: Path, text: str) -> str:
    """Policy-derived config, sanitized (gentle: won't touch globs/commands) —
    matches the existing ``claude_config`` emission precedent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sanitize_sensitive_text(text))
    return str(path)


def compile_claude(policy: AgentPolicy, *, repo: str, out_dir: str | None = None) -> dict[str, str]:
    """Compile ``policy`` for Claude Code; return ``{artifact: path}``."""

    repo_path = Path(repo)
    out = Path(out_dir) if out_dir else repo_path
    hooks = out / ".claude" / "hooks"

    # Persist the exact policy so the runtime hook reads what the lock hashed.
    policy_path = repo_path / "frontier-scout.policy.json"
    save_policy(policy, str(policy_path))
    lock_path = write_lock(policy, str(repo_path), targets=["claude"])

    settings_path = _write_config(
        out / ".claude" / "settings.json",
        json.dumps(build_settings(policy), indent=2) + "\n",
    )
    guard_path = _write_verbatim(hooks / "_fs_guard.py", Path(hook_runtime.__file__).read_text())
    pre_path = _write_verbatim(hooks / "pre_tool_use.py", _PRE_HOOK)
    post_path = _write_verbatim(hooks / "post_tool_use.py", _POST_HOOK)
    managed_path = _write_config(
        out / "managed-settings.json",
        json.dumps(
            to_managed_config_from_names(policy.mcp_server_allowlist), indent=2
        ) + "\n",
    )
    workflow_path = _write_verbatim(
        out / ".github" / "workflows" / "frontier-scout-verify.yml", _WORKFLOW
    )

    return {
        "policy": str(policy_path),
        "lock": lock_path,
        "settings": settings_path,
        "guard": guard_path,
        "pre_hook": pre_path,
        "post_hook": post_path,
        "managed": managed_path,
        "workflow": workflow_path,
    }
