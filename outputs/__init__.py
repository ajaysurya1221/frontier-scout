"""Output renderers for Frontier Scout.

Each module exposes a `render(verdicts: list[dict], **opts) -> str | bytes`
function. The CLI dispatches based on the user's chosen output channel.

Built-in:
    terminal.py  → Rich-formatted CLI output (default)
    html.py      → static HTML report (no JS)

Third-party / optional outputs can land behind feature flags after the local
CLI/report surface is stable.
"""
