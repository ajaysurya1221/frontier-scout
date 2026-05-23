"""Output plugins for Frontier Scout.

Each module exposes a `render(verdicts: list[dict], **opts) -> str | bytes`
function. The CLI dispatches based on the user's chosen output channel.

Built-in:
    terminal.py  → Rich-formatted CLI output (default)
    html.py      → static HTML report (no JS)

Third-party / optional outputs (Slack, Discord, email) will land in v0.3+.
"""
