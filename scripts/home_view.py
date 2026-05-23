"""
App Home dashboard view builder (Round 9).

Renders the persistent Slack App Home tab — a one-look dashboard
showing the bot's state: recent verdicts shipped, MTD cost, channel
taste-model, recent lab activity, latest briefing summary, plus the
next scheduled Scout run.

Design rules (enforced by tests/test_home_view.py):
  • No image blocks. Text + Unicode sparklines beat image blocks on
    speed, accessibility, mobile, and dark-mode for this content.
  • Every section block must carry non-empty text — no blank panels.
  • Partial-data fallback: each section degrades to a placeholder
    rather than crashing, so the dashboard always renders SOMETHING.
  • Pure-stdlib: no new deps, no LLM calls, no network.

Build flow:
  build_view(state: dict) -> dict   # returns the full Slack View JSON

`state` is a dict the Lambda dispatcher assembles from the github
mirror — see lambda/app_home_dispatch.py. Decoupling the data-load
from the view-render lets us unit-test view shape against fixtures
without any I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ── Sparkline + bar-row helpers (the only visualizations we use) ─────────────

# Unicode block-element bar levels. Index 0 is empty, 1..8 fills upward.
_BARS = " ▁▂▃▄▅▆▇█"


def _sparkline(values: list[float] | None, width: int = 8) -> str:
    """Convert a numeric series into an 8-char Unicode sparkline.

    Bins the last `width` values into 8 visual levels (▁..█). Returns a
    flat-low sparkline (no crash) when:
      • `values` is None or empty
      • all values are equal (no range) — flat at the mid level
      • length < width — left-pads with empty cells so trends align
    """
    if not values:
        return "▁" * width
    tail = list(values[-width:])
    lo, hi = min(tail), max(tail)
    rng = hi - lo
    if rng <= 1e-9:
        # Flat series — render as a uniform mid-level so the user sees
        # "no change" rather than the math defaulting to all-zeros.
        # Pad-left so the "newest" data lands on the right, consistent
        # with the rising-series branch below.
        return "▁" * max(0, width - len(tail)) + "▄" * len(tail)
    chars: list[str] = []
    # Left-pad if the series is shorter than the requested width so
    # comparing two sparklines side-by-side aligns on the right edge.
    for _ in range(width - len(tail)):
        chars.append("▁")
    for v in tail:
        # 1..8 (skip the 0/space slot so empty inputs don't render as gaps)
        idx = 1 + min(7, int((v - lo) / rng * 8))
        chars.append(_BARS[idx])
    return "".join(chars)


def _bar_row(value: float, max_value: float, slots: int = 5) -> str:
    """Render a 0..max value as the existing ▰/▱ meter style.

    Matches the readiness meter used in verdict cards so the dashboard
    feels native, not bolted-on.
    """
    if max_value <= 0:
        return "▱" * slots
    filled = round(max(0.0, min(1.0, value / max_value)) * slots)
    return "▰" * filled + "▱" * (slots - filled)


def _humanise_relative_time(ts_iso: str | None) -> str:
    """Return a short relative timestamp like '2 days ago' or 'just now'.

    Robust to missing / malformed inputs — returns 'unknown' rather
    than crashing.
    """
    if not ts_iso:
        return "unknown"
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "unknown"
    delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
    seconds = delta.total_seconds()
    if seconds < 0:
        # Future timestamp — render as "shortly" rather than "−2 days ago"
        return "shortly"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    days = int(seconds // 86400)
    if days == 1:
        return "1 day ago"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


# ── Slack block builders (mirror the helpers in slack_post.py) ───────────────

def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _divider() -> dict:
    return {"type": "divider"}


# ── Section builders ─────────────────────────────────────────────────────────

# Recommendation pills for lab results — match slack_post._LAB_RECOMMENDATION_PILL
_LAB_PILL = {
    "worth_trial": "🟡 worth a TRIAL",
    "monitor":     "⚪ MONITOR",
    "skip":        "🔴 SKIP",
}

_JUDGE_CONFIDENCE_WORD = {
    "high":   "*HIGH*",
    "medium": "*MEDIUM*",
    "low":    "*LOW*",
}

# Budget the cost bar measures against. Matches the operator's stated
# ~$100/month comfort ceiling (also documented in costs guardrails).
_MONTHLY_BUDGET_USD = 100.0


def _this_week_section(state: dict) -> dict:
    """Build the headline "This week" section — shipped count + cost,
    each annotated with a Unicode sparkline of recent history."""
    verdicts_count = int(state.get("verdicts_this_week", 0) or 0)
    verdicts_history = state.get("verdicts_per_week") or []
    cost_mtd = float(state.get("mtd_cost", 0.0) or 0.0)
    cost_history = state.get("cost_per_day_mtd") or []

    return _section(
        f"*This week*\n"
        f"*{verdicts_count}* verdicts shipped   `{_sparkline(verdicts_history)}`   "
        f"_(last {min(len(verdicts_history), 8)} weeks)_\n"
        f"*${cost_mtd:.2f}* spent MTD   `{_sparkline(cost_history)}`   "
        f"`{_bar_row(cost_mtd, _MONTHLY_BUDGET_USD)}` "
        f"_of ${_MONTHLY_BUDGET_USD:.0f} monthly budget_"
    )


def _taste_model_section(state: dict) -> dict:
    """Channel taste-model snapshot. Shows top positive + top negative
    tags with bar-row weights, or a cold-start banner if signal_count_14d
    is below the threshold."""
    prefs = state.get("preferences") or {}
    n = int(prefs.get("signal_count_14d", 0) or 0)

    # Cold-start banner: helpful, not empty.
    if n < 10:
        return _section(
            "*📈 Channel taste model*\n"
            f"_Cold start — {n} signals so far. The bandit will steer the briefing "
            "once we cross 10 reactions/button-clicks in any 14-day window. "
            "React on verdict cards to help train it._"
        )

    reactions = int(prefs.get("reaction_count_14d", 0) or 0)
    labs = int(prefs.get("lab_count_14d", 0) or 0)
    tags = prefs.get("tags") or {}

    pos = sorted(((k, v) for k, v in tags.items() if v >= 0.10),
                 key=lambda kv: -kv[1])[:3]
    neg = sorted(((k, v) for k, v in tags.items() if v <= -0.10),
                 key=lambda kv: kv[1])[:3]

    lines = [
        "*📈 Channel taste model*",
        f"_Tuned by *{reactions}* reactions + *{labs}* lab queues over the last 14 days._",
    ]
    if pos:
        lines.append(
            "Higher interest: " + "  ·  ".join(
                f"*{tag}* `{_bar_row(weight, 1.0)}`" for tag, weight in pos
            )
        )
    if neg:
        lines.append(
            "Lower interest: " + "  ·  ".join(
                f"*{tag}* `{_bar_row(abs(weight), 1.0)}`" for tag, weight in neg
            )
        )
    if not pos and not neg:
        lines.append("_No tags above the ±0.10 noise floor yet._")
    return _section("\n".join(lines))


def _recent_labs_section(state: dict) -> dict | None:
    """Show the 3 most recent lab transcripts. Returns None if no labs
    have run yet (so the caller can skip the section + its divider)."""
    labs = (state.get("recent_labs") or [])[:3]
    if not labs:
        return None
    lines = ["*🧪 Recent labs*"]
    for lab in labs:
        tool = lab.get("tool", "(unknown)")
        rec = lab.get("verdict_for_team", "monitor")
        pill = _LAB_PILL.get(rec, rec.upper())
        when = _humanise_relative_time(lab.get("ran_at"))
        lines.append(f"• *{tool}*  —  {pill}  ·  _{when}_")
    return _section("\n".join(lines))


def _latest_briefing_section(state: dict) -> dict:
    """Show the latest weekly briefing's headline + judge summary."""
    b = state.get("latest_briefing") or {}
    if not b:
        return _section(
            "*📚 Latest briefing*\n"
            "_No briefings yet. The first one ships on the next scheduled "
            "Scout run (or when you trigger one manually from GitHub Actions)._"
        )
    date = b.get("date", "?")
    verdicts = int(b.get("verdicts_count", 0) or 0)
    rating = (b.get("judge_rating") or "medium").lower()
    rating_word = _JUDGE_CONFIDENCE_WORD.get(rating, rating.upper())
    summary = (b.get("judge_summary") or "").strip()
    summary_line = f"\n_{summary}_" if summary else ""
    link = b.get("permalink")
    title = f"<{link}|{date}>" if link else date
    return _section(
        f"*📚 Latest briefing*  —  {title}\n"
        f"*{verdicts}* verdicts  ·  judge confidence {rating_word}{summary_line}"
    )


def _command_hints_section() -> dict:
    """Static command-discovery hint. Slack's App Home doesn't accept
    typed input directly, so the slash commands are shown as text."""
    return _section(
        "*Commands*\n"
        "• `/radar <tool>` — latest verdict on any tool we've evaluated\n"
        "• `/recall <topic>` — semantic search across the radar"
    )


def _footer_context(state: dict) -> dict:
    last_run = _humanise_relative_time(state.get("last_scout_run_at"))
    next_run = state.get("next_scout_at_label") or "next Monday 03:30 UTC"
    commit = state.get("lambda_commit", "")
    branch = state.get("lambda_branch", "")
    deploy_pieces: list[str] = []
    if branch:
        deploy_pieces.append(branch)
    if commit:
        deploy_pieces.append(f"`{commit}`")
    deploy_str = "  ·  Deploy: " + " @ ".join(deploy_pieces) if deploy_pieces else ""
    return _context(
        f"Last Scout: {last_run}  ·  Next: {next_run}{deploy_str}"
    )


# ── Public entry point ───────────────────────────────────────────────────────

def build_view(state: dict | None = None) -> dict[str, Any]:
    """Assemble the full Slack View JSON for `views.publish`.

    `state` is a dict. All keys are optional — missing data degrades to
    a graceful placeholder. The view ALWAYS renders, never empty, never
    broken, even with `state = {}`.

    Returns the full view object suitable for the `view` parameter of
    Slack's `views.publish` API:

      {"type": "home", "blocks": [...]}
    """
    state = state or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    blocks: list[dict] = [
        _header("📡  Frontier Scout — your radar at a glance"),
        _context(f"Updated {now}  ·  data refreshes when you open this tab"),
        _divider(),
        _this_week_section(state),
        _divider(),
        _taste_model_section(state),
    ]

    labs_section = _recent_labs_section(state)
    if labs_section is not None:
        blocks.append(_divider())
        blocks.append(labs_section)

    blocks.append(_divider())
    blocks.append(_latest_briefing_section(state))
    blocks.append(_divider())
    blocks.append(_command_hints_section())
    blocks.append(_divider())
    blocks.append(_footer_context(state))

    return {"type": "home", "blocks": blocks}
