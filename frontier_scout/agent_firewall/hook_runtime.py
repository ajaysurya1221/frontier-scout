"""Self-contained, stdlib-only runtime for Frontier Scout's Claude Code hooks.

THIS MODULE IS COPIED VERBATIM by the compiler into a target repo's
``.claude/hooks/_fs_guard.py`` and imported by the generated ``pre_tool_use.py`` /
``post_tool_use.py``. It therefore MUST NOT import anything from ``frontier_scout``
(it runs wherever Claude Code runs, which need not have the package installed) and
MUST stay pure standard library.

Responsibilities:
  * ``decide(tool_name, tool_input, policy)`` — map a real tool call to a native
    Claude permission decision (``allow`` | ``deny`` | ``ask``), fail-closed.
  * ``handle_pre_tool_use`` — return the PreToolUse ``hookSpecificOutput`` JSON and
    write a redacted action receipt binding the call to the policy hash.
  * ``handle_post_tool_use`` — write a receipt recording the realized outcome.

Frontier Scout emits this; Claude Code enforces it. It never executes the tool.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --- redaction (vendored: stdlib only, no frontier_scout import) -----------------

_SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]+"), "sk-ant-REDACTED"),
    (re.compile(r"sk-[A-Za-z0-9]+"), "sk-REDACTED"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]+"), "xox*-REDACTED"),
    (re.compile(r"ghp_[A-Za-z0-9]+"), "ghp_REDACTED"),
    (re.compile(r"github_pat_[A-Za-z0-9_]+"), "github_pat_REDACTED"),
    (re.compile(r"ATATT[A-Za-z0-9\-_=]+"), "ATATT-REDACTED"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA-REDACTED"),
    (re.compile(r"npm_[A-Za-z0-9]+"), "npm_REDACTED"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer REDACTED"),
]


def scrub(text: str) -> str:
    """Redact common secret shapes from a durable/emitted string."""

    out = text or ""
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


# --- path / glob helpers (recursive-glob approximation, no I/O) -------------------

def _normalise_path(path: str) -> str:
    normalised = path.replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised


def _path_matches_glob(path: str, glob: str) -> bool:
    """Approximate ``**`` recursive-glob semantics with stdlib ``fnmatch``."""

    normalised = _normalise_path(path)
    candidates = [glob]
    if glob.startswith("**/"):
        candidates.append(glob[3:])
    parts = normalised.split("/")
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]
    for candidate in candidates:
        for suffix in suffixes:
            if fnmatch.fnmatch(suffix, candidate):
                return True
    return False


# --- tool-call classification ----------------------------------------------------

_READ_TOOLS = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_NETWORK_TOOLS = {"WebFetch", "WebSearch"}


def _file_path_of(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def decide(tool_name: str, tool_input: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str]:
    """Return ``(decision, reason)`` for a tool call. ``decision`` is allow|deny|ask.

    Fail-closed: anything not provably safe escalates to ``ask`` (and off-policy MCP
    or blocked commands/tools hard-``deny``).
    """

    tool_input = tool_input or {}

    # 1. Hard blocks: an explicitly blocked tool, regardless of args.
    if tool_name in set(policy.get("blocked_tools", [])):
        return "deny", f"Tool '{tool_name}' is on the blocked list."

    # 2. MCP tools (``mcp__<server>__<tool>``): deny-by-default off the allowlist.
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        server = parts[1] if len(parts) > 1 else ""
        if server in set(policy.get("mcp_server_allowlist", [])):
            return "allow", f"MCP server '{server}' is allowlisted."
        return "deny", f"MCP server '{server}' is not on the allowlist (deny-by-default)."

    # 3. Bash: blocked substring -> deny; allowlisted prefix -> allow; else ask.
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        low = command.lower()
        for blocked in policy.get("blocked_shell_commands", []):
            if blocked and blocked.lower() in low:
                return "deny", f"Command matches a blocked pattern: {blocked}"
        for allowed in policy.get("allowed_shell_commands", []):
            if allowed and low.strip().startswith(allowed.lower()):
                return "allow", f"Command matches an allowlisted prefix: {allowed}"
        return "ask", "Command is not on the allowlist; approval required (fail-closed)."

    # 4. File writes/edits: protected glob -> ask; allowed glob -> allow; else ask.
    if tool_name in _WRITE_TOOLS:
        path = _file_path_of(tool_input)
        if any(_path_matches_glob(path, g) for g in policy.get("protected_file_globs", [])):
            return "ask", f"Write touches a protected path: {path}"
        if any(_path_matches_glob(path, g) for g in policy.get("allowed_file_globs", [])):
            return "allow", f"Write is within an allowed path: {path}"
        return "ask", f"Write target is outside any allowed path: {path} (fail-closed)."

    # 5. Reads are allowed (read-only surface).
    if tool_name in _READ_TOOLS:
        return "allow", "Read-only tool."

    # 6. Network egress: approval-gated.
    if tool_name in _NETWORK_TOOLS:
        return "ask", "Network egress requires approval."

    # 7. Explicitly allowlisted tool.
    if tool_name in set(policy.get("allowed_tools", [])):
        return "allow", f"Tool '{tool_name}' is allowlisted."

    # 8. Unknown tool: fail-closed.
    return "ask", f"Tool '{tool_name}' is not classified; approval required (fail-closed)."


# --- receipts (raw JSON; schema-compatible with frontier_scout Receipt) ----------

_VERDICT_OF = {"allow": "allow", "ask": "needs_approval", "deny": "block"}
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text).lower()[:40].strip("-") or "action"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _input_hash(tool_input: dict[str, Any]) -> str:
    canonical = json.dumps(tool_input or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def receipts_dir(repo: str) -> Path:
    return Path(repo) / ".frontier-scout" / "receipts"


def _write(repo: str, receipt: dict[str, Any], phase: str) -> str:
    directory = receipts_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    receipt_id = receipt["receipt_id"]
    path = directory / f"{receipt_id}-{phase}.json"
    path.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    return str(path)


def handle_pre_tool_use(
    event: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_hash: str,
    repo: str,
    version: str | None = None,
) -> dict[str, Any]:
    """Decide on a PreToolUse event, write an action receipt, return the hook JSON."""

    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}
    decision, reason = decide(tool_name, tool_input, policy)
    files = [_file_path_of(tool_input)] if _file_path_of(tool_input) else []
    receipt = {
        "receipt_id": f"{_stamp()}-{_slug(tool_name)}",
        "timestamp": datetime.now(UTC).isoformat(),
        "repo": repo,
        "task_summary": scrub(f"{tool_name}: {json.dumps(tool_input, default=str)}")[:500],
        "verdict": _VERDICT_OF.get(decision, "needs_approval"),
        "decision": decision,
        "kind": "agent-action",
        "policy_hash": policy_hash,
        "tool_name": tool_name,
        "tool_input_hash": _input_hash(tool_input),
        "reasons": [{"severity": "info", "rule_id": f"tool.{decision}", "message": scrub(reason)}],
        "files_considered": [scrub(f) for f in files],
        "required_checks": list(policy.get("required_checks", [])),
        "warnings": [],
        "frontier_scout_version": version,
        "realized": None,
    }
    _write(repo, receipt, phase="pre")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": scrub(reason),
        }
    }


def handle_post_tool_use(
    event: dict[str, Any],
    *,
    policy_hash: str,
    repo: str,
    version: str | None = None,
) -> dict[str, Any]:
    """Record the realized outcome of a completed tool call as an action receipt."""

    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}
    tool_output = event.get("tool_output")
    files = [_file_path_of(tool_input)] if _file_path_of(tool_input) else []
    realized: dict[str, Any] = {"completed": True}
    if isinstance(tool_output, dict):
        realized["status"] = tool_output.get("status")
    receipt = {
        "receipt_id": f"{_stamp()}-{_slug(tool_name)}",
        "timestamp": datetime.now(UTC).isoformat(),
        "repo": repo,
        "task_summary": scrub(f"{tool_name}: {json.dumps(tool_input, default=str)}")[:500],
        "verdict": "allow",
        "decision": "allow",
        "kind": "agent-action",
        "policy_hash": policy_hash,
        "tool_name": tool_name,
        "tool_input_hash": _input_hash(tool_input),
        "reasons": [],
        "files_considered": [scrub(f) for f in files],
        "required_checks": [],
        "warnings": [],
        "frontier_scout_version": version,
        "realized": realized,
    }
    _write(repo, receipt, phase="post")
    return {}
