"""Advisory policy-snippet exporters (static research preview).

Pure builders that render an :class:`~frontier_scout.agent_firewall.models.AgentPolicy`
into human-readable governance snippets — a ``CLAUDE.md`` block, an ``AGENTS.md`` block,
and a PR checklist. Every snippet carries an *advisory* header: Frontier Scout **emits**
this guidance, it does **not** enforce it at runtime.

These are output *formats* (not coding-assistant clients), so — unlike the sanctioned-pack
``exporters/claude_config.py`` flow — they are deliberately **not** routed through the
``--client`` hard-gate. ``export_policy_snippets`` redacts every snippet through
``sanitize_sensitive_text`` at the write boundary.
"""

from __future__ import annotations

from pathlib import Path

from frontier_scout.agent_firewall.models import AgentPolicy
from outputs._text import sanitize_sensitive_text

__all__ = [
    "build_claude_md_snippet",
    "build_agents_md_snippet",
    "build_pr_checklist",
    "export_policy_snippets",
]

_ADVISORY_NOTE = (
    "Advisory — Frontier Scout emits this guidance from a static repo scan; "
    "it does not enforce it at runtime. Treat it as a review aid, not a control."
)


def _bullet_list(items: list[str]) -> str:
    """Render ``items`` as a markdown bullet list, or a placeholder when empty."""

    if not items:
        return "- (none)\n"
    return "".join(f"- {item}\n" for item in items)


def _policy_sections(policy: AgentPolicy) -> str:
    """The shared body shared by the CLAUDE.md and AGENTS.md snippets."""

    parts = [
        "### Allowed tools\n",
        _bullet_list(policy.allowed_tools),
        "\n### Blocked tools\n",
        _bullet_list(policy.blocked_tools),
        "\n### Blocked shell commands\n",
        _bullet_list(policy.blocked_shell_commands),
        "\n### Protected paths\n",
        _bullet_list(policy.protected_file_globs),
        "\n### MCP server allowlist\n",
        _bullet_list(policy.mcp_server_allowlist),
        "\n### Approval gates\n",
        _bullet_list(policy.approval_gates),
        "\n### Required checks\n",
        _bullet_list(policy.required_checks),
    ]
    return "".join(parts)


def build_claude_md_snippet(policy: AgentPolicy) -> str:
    """Render the advisory ``CLAUDE.md`` policy block."""

    return (
        "## Agent policy (advisory — Frontier Scout emits this; "
        "it does not enforce it)\n\n"
        f"> {_ADVISORY_NOTE}\n\n"
        f"{_policy_sections(policy)}"
    )


def build_agents_md_snippet(policy: AgentPolicy) -> str:
    """Render the same content tuned for ``AGENTS.md``."""

    return (
        "## Agent adoption policy (advisory)\n\n"
        f"> {_ADVISORY_NOTE}\n\n"
        "Agents working in this repo should observe the following advisory policy. "
        "These rules are emitted from a static scan and are not enforced at runtime.\n\n"
        f"{_policy_sections(policy)}"
    )


def build_pr_checklist(policy: AgentPolicy) -> str:
    """Render a markdown checkbox list of required checks + approval reminders."""

    lines = ["# Agent change checklist\n", "\n"]
    lines.append("> " + _ADVISORY_NOTE + "\n\n")
    for check in policy.required_checks:
        lines.append(f"- [ ] Run `{check}`\n")
    for gate in policy.approval_gates:
        lines.append(f"- [ ] Human approval obtained for: {gate}\n")
    if not policy.required_checks and not policy.approval_gates:
        lines.append("- [ ] (no required checks or approval gates detected)\n")
    lines.append(
        "\n_This checklist is static and advisory — Frontier Scout emits it; "
        "it does not enforce it._\n"
    )
    return "".join(lines)


def export_policy_snippets(
    policy: AgentPolicy,
    target_dir: str,
    formats: list[str] | None = None,
) -> dict[str, str]:
    """Write the selected redacted snippet(s) to ``target_dir``; return ``{name: path}``.

    ``formats`` selects which snippets to emit (any of ``"claude"``, ``"agents-md"``,
    ``"pr-checklist"``); ``None`` emits all three.
    """

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    snippets: list[tuple[str, str, str]] = [
        ("claude", build_claude_md_snippet(policy), "CLAUDE.policy.md"),
        ("agents-md", build_agents_md_snippet(policy), "AGENTS.policy.md"),
        ("pr-checklist", build_pr_checklist(policy), "PR-CHECKLIST.md"),
    ]
    out: dict[str, str] = {}
    for name, text, fname in snippets:
        if formats is not None and name not in formats:
            continue
        path = target / fname
        path.write_text(sanitize_sensitive_text(text))
        out[name] = str(path)
    return out
