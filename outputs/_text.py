"""Shared text utilities.

Salvaged from the legacy `scripts/slack_post.py` (now deleted) — these
clip / escape / sanitize helpers are not Slack-specific and are reused
across the terminal output, the HTML report, and the MCP server's
tool responses.
"""

from __future__ import annotations

import re


def clip(text: str | None, max_chars: int) -> str:
    """Trim ``text`` to ``max_chars`` with an ellipsis, normalizing whitespace.

    Returns an empty string for ``None`` / empty input.
    """
    s = " ".join((text or "").strip().split())
    if len(s) <= max_chars:
        return s
    if max_chars < 2:
        return s[:max_chars]
    return s[: max_chars - 1].rstrip() + "…"


def escape_html(text: str | None) -> str:
    """Escape the four characters that matter inside an HTML body.

    Conservative: we do NOT escape quotes, because consumers wrap with
    ``<pre>`` / text nodes — never as attribute values. Pass through
    apostrophes intentionally so generated copy reads naturally.
    """
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# Patterns whose matches must be redacted from any log line that could
# end up in a public artifact (briefing markdown, GitHub Actions log,
# bug-report attachment, etc.). Keep in sync with the equivalent table
# in any future `outputs/slack.py` plugin.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "sk-ant-REDACTED"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-REDACTED"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]+"), "xox*-REDACTED"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_REDACTED"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat_REDACTED"),
    (re.compile(r"ATATT[A-Za-z0-9\-_=]{20,}"), "ATATT-REDACTED"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer REDACTED"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA-REDACTED"),
    (re.compile(r"npm_[A-Za-z0-9]{30,}"), "npm_REDACTED"),
)


def sanitize_sensitive_text(text: str | None) -> str:
    """Redact common secret shapes from a log / error string.

    Use before printing anything that includes a captured exception
    body or external response payload — Anthropic keys, GitHub PATs,
    Slack tokens, AWS access keys, npm tokens, and bearer headers are
    all collapsed to a placeholder.
    """
    out = text or ""
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out
