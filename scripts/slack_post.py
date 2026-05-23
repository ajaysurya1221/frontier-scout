"""
Slack Block Kit formatter for Scout, Pulse, Synth, and cost reports.

Set DRY_RUN=1 to print the payload instead of sending — used in tests and local dev.
Auth (auto-detected in order):
  1. SLACK_WEBHOOK_URL — Incoming Webhook (simplest, no admin approval needed)
  2. SLACK_BOT_TOKEN that starts with https://hooks.slack.com/ — auto-routed to webhook
  3. SLACK_BOT_TOKEN (xoxb-...) + SLACK_CHANNEL_ID — Bot token via slack-sdk

Round 3 additions:
  - retry with exponential backoff on transient failures
  - dead-letter queue at .scratch/slack-dead-letter.jsonl when retries exhausted
  - URL allowlist on rendered hyperlinks (validators.domain_allowed)

Round 4 additions:
  - weekly_briefing_threaded(): parent TL;DR + per-verdict colored thread cards
  - bot-authored 🧪 / 👍 / 👎 reactions on each thread card (requires
    `reactions:write` scope on the bot token)
  - Routing in scout.py picks threaded format when bot token + channel ID
    are set; webhook path keeps the single-message format
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from validators import domain_allowed

DEAD_LETTER = Path(__file__).parent.parent / ".scratch" / "slack-dead-letter.jsonl"
# Briefings dir — committed alongside the briefing markdown. Tests redirect
# this via monkeypatch to avoid polluting the repo with stray meta files.
BRIEFINGS_DIR = Path(__file__).parent.parent / "briefings"

CATEGORY_EMOJI = {
    "frontier_model": "🧠 Frontier Models",
    "orchestration":  "🤖 Orchestration",
    "tool":           "🛠️ Tools & Frameworks",
    "data":           "📊 Data Ecosystem",
    "compute":        "⚡ Compute & Hardware",
    "security":       "🔐 Security & Compliance",
}

CATEGORY_LABEL = {
    "frontier_model": "Frontier Models",
    "orchestration":  "Orchestration",
    "tool":           "Tools & Frameworks",
    "data":           "Data Ecosystem",
    "compute":        "Compute & Hardware",
    "security":       "Security & Compliance",
}

VERDICT_EMOJI = {
    "adopt":  "🟢 ADOPT",
    "trial":  "🟡 TRIAL",
    "assess": "⚪ ASSESS",
    "hold":   "🔴 HOLD",
}

VERDICT_LABEL = {
    "adopt":  "ADOPT",
    "trial":  "TRIAL",
    "assess": "ASSESS",
    "hold":   "HOLD",
}

SOC2_BADGE = {
    "safe":        "✅ SOC2-safe",
    "conditional": "⚠️ SOC2-conditional",
    "blocked":     "❌ SOC2-blocked",
}

SOC2_LABEL = {
    "safe": "SOC2-safe",
    "conditional": "SOC2-conditional",
    "blocked": "SOC2-blocked",
}

SEVERITY_ICON = {
    "critical": "🔥",
    "high":     "⭐",
    "standard": "📌",
}

TIER_HEADER = {
    "adopt":  "━━━━━━━━━━  🟢 ADOPT  ━━━━━━━━━━",
    "trial":  "━━━━━━━━━━  🟡 TRIAL  ━━━━━━━━━━",
    "assess": "━━━━━━━━━━  ⚪ ASSESS  ━━━━━━━━━━",
    "hold":   "━━━━━━━━━━  🔴 HOLD  ━━━━━━━━━━",
}

# Slack attachment color bars by tier — render as a colored vertical accent
# next to each threaded verdict card.
TIER_COLOR = {
    "adopt":  "#36a64f",   # green
    "trial":  "#f2c744",   # amber
    "assess": "#9aa0a6",   # gray
    "hold":   "#d93025",   # red
}

TIER_ORDER = ["adopt", "trial", "assess", "hold"]

# Reactions the bot auto-adds to each threaded verdict card (Slack emoji names,
# without the wrapping colons).
DEFAULT_VERDICT_REACTIONS = ("test_tube", "+1", "-1")

# Bot identity override on the parent post — the message renders as
# "Frontier Scout 📡" instead of the generic Slack-app name, with a satellite
# icon. Subtle but the system feels more like a product than a script.
BOT_DISPLAY_NAME = "Frontier Scout"
BOT_ICON_EMOJI = ":satellite_antenna:"

def _verdict_marker(n: int) -> str:
    """Display marker for the Nth verdict — small inline-code `#N` pill.

    Previously rendered as chunky Slack keycap emojis (1️⃣ 2️⃣ …) which look
    cheap and dated (Discord-era). Backtick-wrapped `#N` renders as a tight
    monospace pill — same scannability, much better typographic polish.
    """
    return f"`#{n}`"

JUDGE_CONFIDENCE = {
    "high":   "🤖 judge confidence: *HIGH*",
    "medium": "🤖 judge confidence: *medium*",
    "low":    "🤖 judge confidence: *low* — review before sharing",
}


_MAX_JUDGE_SUMMARY_CHARS = 320
_MAX_PARENT_HIGHLIGHTS = 5
_MAX_PARENT_ACTIONS = 3
_MAX_LINE_CHARS = 220


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _divider() -> dict:
    return {"type": "divider"}


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _readiness_meter(level: int) -> str:
    """Return a 5-slot ▰/▱ meter. Level 0-5."""
    level = max(0, min(5, level))
    return "▰" * level + "▱" * (5 - level)


def _clip(text: str | None, max_chars: int) -> str:
    """Trim text to max_chars with ellipsis and normalized whitespace."""
    s = " ".join((text or "").strip().split())
    if len(s) <= max_chars:
        return s
    if max_chars < 2:
        return s[:max_chars]
    return s[: max_chars - 1].rstrip() + "…"


def _escape_mrkdwn(text: str | None) -> str:
    """Escape Slack mrkdwn control chars."""
    escaped = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Prevent accidental channel-wide pings from model/user-provided text.
    escaped = re.sub(r"@(?=channel\b|here\b|everyone\b)", "@\u200b", escaped, flags=re.I)
    escaped = escaped.replace("&lt;!channel&gt;", "&lt;!\u200bchannel&gt;")
    escaped = escaped.replace("&lt;!here&gt;", "&lt;!\u200bhere&gt;")
    escaped = escaped.replace("&lt;!everyone&gt;", "&lt;!\u200beveryone&gt;")
    return escaped


def _sanitize_sensitive_text(text: str) -> str:
    """Redact common secret-bearing values from logs."""
    redacted = text or ""
    patterns = [
        (r"https://hooks\.slack\.com/services/[^\s'\"`]+", "https://hooks.slack.com/services/****"),
        (r"https://hooks\.slack\.com/actions/[^\s'\"`]+", "https://hooks.slack.com/actions/****"),
        (r"xox[baprs]-[A-Za-z0-9-]+", "xox*-REDACTED"),
        (r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer REDACTED"),
    ]
    for pattern, repl in patterns:
        redacted = re.sub(pattern, repl, redacted)
    return redacted


def _compact_badges(v: dict) -> str:
    """One-line textual badges for tier/severity/soc2/readiness."""
    tier = VERDICT_LABEL.get(v.get("verdict", "assess"), "ASSESS")
    sev = (v.get("severity", "standard") or "standard").capitalize()
    soc2 = SOC2_LABEL.get(v.get("soc2", "conditional"), "SOC2-conditional")
    readiness = int(v.get("readiness", 3))
    return f"{tier} · {sev} · {soc2} · Readiness {readiness}/5"


def _a11y_label(text: str, max_chars: int = 75) -> str:
    """Constrain accessibility labels to conservative Slack-safe length."""
    return _clip(text, max_chars)


# ── rich_text block helpers (Round 8) ────────────────────────────────────────
#
# Slack's `rich_text` block type supports proper bulleted lists, blockquotes,
# inline styled spans, and code blocks — far better mobile rendering than the
# older mrkdwn-in-section approach. We adopt it for the TL;DR list, judge's
# read quote, lab-reply code excerpt, and verdict-card body. Everywhere else
# (headers, context strips, fields layouts) stays on `section`+mrkdwn because
# `rich_text` would be overkill for those.

def _rich_text(*elements: dict) -> dict:
    """Top-level rich_text block wrapping the given child elements
    (rich_text_section / rich_text_list / rich_text_quote / rich_text_preformatted)."""
    return {"type": "rich_text", "elements": list(elements)}


def _rt_section(*spans: dict) -> dict:
    """rich_text_section containing inline spans (text, link, emoji)."""
    return {"type": "rich_text_section", "elements": list(spans)}


def _rt_quote(*spans: dict) -> dict:
    """rich_text_quote — proper blockquote rendering, consistent across
    web/desktop/mobile (vs the `> ` mrkdwn prefix which varies)."""
    return {"type": "rich_text_quote", "elements": list(spans)}


def _rt_list(style: str, *bullets: dict, indent: int = 0) -> dict:
    """rich_text_list. style is 'bullet' or 'ordered'. Each bullet is a
    rich_text_section. Bullets render with platform-native indent —
    no whitespace-string trickery."""
    return {
        "type": "rich_text_list",
        "style": style,
        "indent": indent,
        "elements": list(bullets),
    }


def _rt_preformatted(text: str) -> dict:
    """rich_text_preformatted — monospace code block. Used in the lab reply
    to show the actual test excerpt that ran (proof, not theater)."""
    return {
        "type": "rich_text_preformatted",
        "elements": [{"type": "text", "text": text}],
    }


def _rt_text(text: str, *, bold: bool = False, italic: bool = False,
             code: bool = False, strike: bool = False) -> dict:
    """Inline text span with optional styling."""
    style = {}
    if bold:    style["bold"] = True
    if italic:  style["italic"] = True
    if code:    style["code"] = True
    if strike:  style["strike"] = True
    out: dict = {"type": "text", "text": text}
    if style:
        out["style"] = style
    return out


def _rt_link(url: str, text: str, *, bold: bool = False) -> dict:
    """Inline link span. `alt_text` is implicit via the link `text` field —
    screen readers announce the visible text, so we don't need a separate
    alt_text on each link."""
    out: dict = {"type": "link", "url": url, "text": text}
    if bold:
        out["style"] = {"bold": True}
    return out


# ── Section-block accessories (Round 8) ──────────────────────────────────────

def _image_accessory(source_url: str, category: str = "tool",
                     alt_text: str | None = None) -> dict | None:
    """Build a section block `accessory` dict pointing at the tool's logo.

    Logic:
      • github.com/<org>/<repo>  →  https://github.com/<org>.png?size=120
      • huggingface.co/<user>/…   →  https://huggingface.co/avatars/<user>.png
      • anything else             →  None (caller renders without accessory)

    GitHub serves an identicon (auto-generated 4×4 grid) for personal accounts
    that have no custom avatar — we accept those rather than skipping the
    accessory entirely. The identicon at least gives consistent visual rhythm
    down the card list.

    All accessories carry `alt_text` for screen-reader users — falls back to
    the org/user name if no explicit alt provided.
    """
    if not source_url:
        return None

    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/", source_url)
    if m:
        org = m.group(1)
        return {
            "type": "image",
            "image_url": f"https://github.com/{org}.png?size=120",
            "alt_text": alt_text or f"{org} avatar",
        }

    m = re.match(r"https?://huggingface\.co/([^/]+)/", source_url)
    if m:
        user = m.group(1)
        return {
            "type": "image",
            "image_url": f"https://huggingface.co/avatars/{user}.png",
            "alt_text": alt_text or f"{user} avatar on Hugging Face",
        }

    return None


# ── Hero takeaway line (Round 8) ─────────────────────────────────────────────

# Maximum length for the hero "why_it_matters" prose before we trim with an
# ellipsis. Picked so a typical card renders at ~2 lines on desktop, ~3 on
# narrow mobile widths.
_HERO_PROSE_MAX = 180


def _hero_takeaway(why_it_matters: str) -> str:
    """Trim `why_it_matters` to the first sentence (or first 180 chars) so
    the hero line stays scannable. Preserves trailing punctuation when
    cleanly cut at a sentence boundary; appends an ellipsis otherwise."""
    text = (why_it_matters or "").strip()
    if not text or len(text) <= _HERO_PROSE_MAX:
        return text
    # Prefer a sentence boundary near the cap
    cap = _HERO_PROSE_MAX
    cut = text[:cap].rfind(". ")
    if cut > 80:
        return text[:cut + 1]
    # Fallback: hard cut at the cap, trim trailing whitespace, append ellipsis
    return text[:cap].rstrip() + "…"


# ── Memory trend lookup (Round 8) ────────────────────────────────────────────

def _memory_trend_text(tool: str, current_verdict: str) -> str | None:
    """Render a one-line "ASSESS (Mar 14) → TRIAL (today)" trend if Mem0
    holds a prior verdict for this tool. Returns None on any failure —
    caller skips the trend block silently."""
    try:
        from memory import is_available, mem
    except Exception:
        return None
    if not is_available():
        return None
    try:
        prior = mem.prior_verdict(tool, days=180, threshold=0.85)
    except Exception:
        return None
    if not prior:
        return None
    prior_v = (prior.get("verdict") or "").upper()
    if not prior_v or prior_v == (current_verdict or "").upper():
        # Either no prior verdict word, or trajectory is flat — skip.
        return None
    prior_iso = prior.get("added_at") or ""
    prior_date = "earlier"
    if prior_iso:
        try:
            d = datetime.fromisoformat(prior_iso.replace("Z", "+00:00"))
            prior_date = d.strftime("%b %d")
        except (ValueError, TypeError):
            pass
    return (
        f"🧠  Memory: *{prior_v}* ({prior_date})  →  "
        f"*{current_verdict.upper()}* (today)"
    )


def _safe_link(url: str, text: str) -> str:
    """Render a Slack hyperlink only if the URL's domain is in the allowlist.

    Untrusted/unknown domains fall back to plain text (non-clickable).
    """
    label = _escape_mrkdwn(text)
    if not url:
        return f"*{label}*"
    if domain_allowed(url):
        return f"<{url}|{label}>"
    return f"*{label}*"


def _tier_counts(verdicts: list[dict]) -> dict[str, int]:
    counts = {t: 0 for t in TIER_ORDER}
    for v in verdicts:
        tier = v.get("verdict", "assess")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _severity_counts(verdicts: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "standard": 0}
    for v in verdicts:
        sev = v.get("severity", "standard")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _sorted_verdicts(verdicts: list[dict]) -> list[dict]:
    tier_rank = {tier: i for i, tier in enumerate(TIER_ORDER)}
    sev_rank = {"critical": 0, "high": 1, "standard": 2}
    return sorted(
        verdicts,
        key=lambda v: (
            tier_rank.get(v.get("verdict", "assess"), 99),
            sev_rank.get(v.get("severity", "standard"), 99),
            -(int(v.get("readiness", 3))),
            (v.get("tool_name") or "").lower(),
        ),
    )


def _parent_action_lines(verdicts: list[dict], limit: int = _MAX_PARENT_ACTIONS) -> list[str]:
    lines: list[str] = []
    for v in _sorted_verdicts(verdicts):
        action = _clip(v.get("next_action", ""), 110)
        tool = _clip(v.get("tool_name", "Tool"), 40)
        if action:
            lines.append(f"{tool}: {action}")
        if len(lines) >= limit:
            break
    if lines:
        return lines
    return ["Review thread verdict cards and pick one lab candidate."]


def _briefing_overview_blocks(
    *,
    date: str,
    scanned: int,
    cost: float,
    verdicts: list[dict],
    judge_rating: str,
    judge_summary: str,
    dedup_drops: int,
    prior_drops: int,
    duration_s: float | None = None,
    top_k: int = _MAX_PARENT_HIGHLIGHTS,
) -> list[dict]:
    """Shared parent summary for webhook and threaded briefing surfaces."""
    considered = max(0, scanned - dedup_drops - prior_drops)
    shipped = len(verdicts)
    tiers = _tier_counts(verdicts)
    severities = _severity_counts(verdicts)
    judge_word = (judge_rating or "medium").upper()
    duration_str = f"{int(duration_s)}s" if duration_s else "n/a"

    summary = _clip(
        judge_summary
        or "Signals were evaluated against stack fit, SOC2 risk, and execution value.",
        _MAX_JUDGE_SUMMARY_CHARS,
    )
    actions = _parent_action_lines(verdicts)
    action_lines = "\n".join(f"• {_escape_mrkdwn(line)}" for line in actions)

    blocks: list[dict] = [
        _header(f"Frontier Scout — Weekly Briefing · {date}"),
        _section(
            "*What happened*\n"
            f"{scanned} scanned → {considered} considered → {shipped} shipped\n\n"
            "*Why it matters*\n"
            f"{_escape_mrkdwn(summary)}\n\n"
            "*What to do next*\n"
            f"{action_lines}"
        ),
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "*Pipeline*\n"
                        f"Judge {judge_word}\n"
                        f"Cost ${cost:.4f}\n"
                        f"Runtime {duration_str}"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        "*Decision Mix*\n"
                        f"{tiers.get('adopt', 0)} ADOPT · {tiers.get('trial', 0)} TRIAL · "
                        f"{tiers.get('assess', 0)} ASSESS · {tiers.get('hold', 0)} HOLD\n"
                        f"{severities.get('critical', 0)} critical · "
                        f"{severities.get('high', 0)} high · "
                        f"{severities.get('standard', 0)} standard"
                    ),
                },
            ],
        },
    ]

    tuned_line = _tuned_by_line()
    if tuned_line:
        blocks.append(_context(tuned_line))
    blocks.append(_divider())

    ranked = _sorted_verdicts(verdicts)
    highlights = ranked[:top_k]
    if highlights:
        bullets: list[dict] = []
        for v in highlights:
            url = v.get("source_url", "")
            tool = _clip(v.get("tool_name", "Tool"), 70)
            takeaway = _clip(
                _hero_takeaway(v.get("why_it_matters", "")) or v.get("what", ""),
                140,
            )
            spans = []
            if url and domain_allowed(url):
                spans.append(_rt_link(url, tool, bold=True))
            else:
                spans.append(_rt_text(tool, bold=True))
            if takeaway:
                spans.append(_rt_text(f" — {takeaway}"))
            spans.append(_rt_text(f"\n  {_compact_badges(v)}"))
            bullets.append(_rt_section(*spans))

        blocks.append(_section("*Top findings*"))
        blocks.append(_rich_text(_rt_list("ordered", *bullets)))

    hidden_count = max(0, shipped - len(highlights))
    if hidden_count:
        blocks.append(_context(f"{hidden_count} additional verdicts are available in the thread."))
    blocks.append(
        _context("Full verdict cards and actions are in thread · `/radar <tool>` · `/recall <topic>`")
    )
    return blocks


def weekly_briefing_blocks(
    date: str,
    scanned: int,
    cost: float,
    verdicts: list[dict],
    judge_rating: str = "medium",
    judge_summary: str = "",
    dedup_drops: int = 0,
    prior_drops: int = 0,
) -> list[dict]:
    return _briefing_overview_blocks(
        date=date,
        scanned=scanned,
        cost=cost,
        verdicts=verdicts,
        judge_rating=judge_rating,
        judge_summary=judge_summary,
        dedup_drops=dedup_drops,
        prior_drops=prior_drops,
        duration_s=None,
        top_k=6,
    )


def pulse_blocks(
    source: str,
    title: str,
    url: str,
    when: str,
    verdict: dict | None = None,
) -> list[dict]:
    """Build Slack blocks for a Tier-S Pulse alert.

    Round 8 redesign — same design dialect as the Scout verdict cards:
    bold-text labels (no emoji-as-labels), takeaway as hero, metadata
    strip beneath, severity icon as a status badge only.
    """
    sev = (verdict or {}).get("severity", "high")
    sev_icon = SEVERITY_ICON.get(sev, "⭐")
    link = _safe_link(url, title)

    blocks: list[dict] = [
        _section(f"*⚡  Tier-S Drop · {source}*  ·  _{when}_"),
    ]

    if verdict:
        why_takeaway = _hero_takeaway(verdict.get("why_it_matters", ""))
        readiness = int(verdict.get("readiness", 3))
        meter = _readiness_meter(readiness)
        # Hero: bold link + why-it-matters takeaway + severity icon trail
        blocks.append(_section(
            f"*{link}* — {why_takeaway}   {sev_icon}"
        ))
        # Metadata strip — verdict tier word + category + SOC2 + readiness
        blocks.append(_context(
            f"{VERDICT_EMOJI[verdict['verdict']]}  ·  "
            f"{CATEGORY_EMOJI[verdict['category']]}  ·  "
            f"{SOC2_BADGE[verdict['soc2']]}  ·  "
            f"Readiness `{meter}` {readiness}/5"
        ))
        # Next-action gets its own block — operationally the most
        # important line on the whole alert.
        blocks.append(_section(f"*Next action* — {verdict['next_action']}"))
    else:
        # No verdict — just the headline link, no metadata
        blocks.append(_section(link))

    blocks.append(_context(
        "React: 👍 worth my time  ·  👎 skip  ·  🧪 lab it"
    ))
    return blocks


def synth_blocks(month: str, synthesis: dict) -> list[dict]:
    """Build Slack blocks for the monthly synthesis.

    Round 8 redesign — bold-text labels, no emoji-as-labels, single
    divider rule between sections (was four). Uses rich_text bullet
    lists for the Momentum check so it renders consistently across
    web/desktop/mobile (vs the older `• ` mrkdwn convention).
    """
    focus = synthesis["focus_this_month"]
    adopted   = synthesis.get("adopted", []) or []
    stalled   = synthesis.get("stalled", []) or []
    blind     = synthesis.get("blind_spots", []) or []

    def _kv_bullet(label: str, items: list[str]) -> dict:
        """One rich_text_section showing 'Label: a, b, c' or 'Label: none'."""
        joined = ", ".join(items) if items else "—"
        return _rt_section(
            _rt_text(label, bold=True),
            _rt_text(f": {joined}"),
        )

    return [
        _header(f"📊  Frontier Scout — Monthly Synthesis · {month}"),
        _section(
            f"*What you've been exploring*\n{synthesis['exploration_summary']}"
        ),
        _divider(),
        _rich_text(_rt_list(
            "bullet",
            _kv_bullet("Adopted",     adopted),
            _kv_bullet("Stalled",     stalled),
            _kv_bullet("Blind spots", blind),
        )),
        _divider(),
        _section(
            f"*Focus this month — {focus['tool']}*\n"
            f"{focus['rationale']}\n\n"
            f"*Lab suggestion* — {focus['lab_suggestion']}"
        ),
        _section(f"*Org opportunity* — {synthesis['org_opportunity']}"),
    ]


def cost_report_blocks(month: str, mtd: float, limit: float = 10.0) -> list[dict]:
    pct = (mtd / limit) * 100 if limit else 0
    alert = "🚨 " if mtd > limit * 0.5 else "💰 "
    return [
        _section(
            f"{alert}*Frontier Scout — Cost Report*\n"
            f"_{month}_ spend: *${mtd:.4f}* / ${limit:.2f} limit  (`{pct:.1f}%`)"
        ),
    ]


def _write_dead_letter(blocks: list[dict], err: str) -> None:
    """Append the failed payload to .scratch/slack-dead-letter.jsonl."""
    DEAD_LETTER.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "error": _sanitize_sensitive_text(str(err))[:500],
        "blocks": blocks,
    }
    with DEAD_LETTER.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _do_post(blocks: list[dict], thread_ts: str | None) -> str | None:
    """One attempt at posting. Raises on failure.

    Routing precedence (bot wins so the richer path is preferred):
      1. SLACK_BOT_TOKEN (xoxb-...) + SLACK_CHANNEL_ID  → bot mode
      2. SLACK_WEBHOOK_URL                              → webhook mode
      3. SLACK_BOT_TOKEN that's actually a webhook URL  → webhook mode (paste-into-wrong-var)
      4. Nothing                                        → RuntimeError
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "")

    # 1. Bot wins when both are set — that's the explicit upgrade path.
    use_bot = bot_token.startswith("xoxb-") and bool(channel_id)

    # 3. Tolerate the common mistake of pasting a webhook URL into SLACK_BOT_TOKEN
    if not use_bot and not webhook_url and bot_token.startswith("https://hooks.slack.com/"):
        webhook_url = bot_token
        bot_token = ""

    if use_bot:
        from slack_sdk import WebClient
        print(f"  Slack target: BOT (channel={channel_id!r})")
        client = WebClient(token=bot_token)
        resp = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            thread_ts=thread_ts,
            text="Frontier Scout update",
        )
        ok = resp.get("ok", False)
        if not ok:
            raise RuntimeError(
                f"Slack chat.postMessage returned ok=false: error={resp.get('error')!r} "
                f"channel={channel_id!r}"
            )
        print(f"  ✅ Slack bot accepted (ts={resp.get('ts')!r})")
        return resp["ts"]

    if webhook_url:
        import requests
        # Mask the secret token segment of the webhook URL in logs
        masked = webhook_url.rsplit("/", 1)[0] + "/****"
        print(f"  Slack target: WEBHOOK ({masked})")
        if bot_token.startswith("xoxb-") and not channel_id:
            print("  ⚠️  bot token present but SLACK_CHANNEL_ID missing — falling back to webhook")
        payload: dict = {"blocks": blocks, "text": "Frontier Scout update"}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()

        # Slack webhooks return 200 OK with body 'ok' on real success. On
        # several real failure modes (channel archived, app uninstalled,
        # invalid_payload, no_team) Slack still returns 200 but the body
        # contains an error string. Treat anything other than 'ok' as a
        # delivery failure — otherwise the pipeline reports green while
        # nothing reaches Slack.
        body = (resp.text or "").strip()
        if body and body != "ok":
            raise RuntimeError(
                f"Slack webhook returned 200 but body is {body!r} "
                f"(expected 'ok'). Most common causes: invalid_payload, "
                f"channel_not_found, no_team, action_disabled."
            )
        print(f"  ✅ Slack webhook accepted (HTTP {resp.status_code} · body={body!r})")
        return None  # webhooks don't return a ts

    raise RuntimeError(
        "No Slack credentials. Set SLACK_BOT_TOKEN (xoxb-...) + SLACK_CHANNEL_ID "
        "(recommended; unlocks threaded format + auto-reactions), or "
        "SLACK_WEBHOOK_URL (single-message fallback)."
    )


# ── Shared retry helper ──────────────────────────────────────────────────────

def _with_slack_retry(
    fn,
    *args,
    max_retries: int = 3,
    dead_letter_payload: dict | None = None,
    op_label: str = "slack",
    **kwargs,
):
    """Run a Slack API call with exponential backoff. On exhaustion, write
    dead-letter (if a payload is provided) and re-raise the last exception.

    Used by both single-message `post()` and the new threaded helpers below.
    """
    delays = [1, 4, 16]
    non_retryable_markers = (
        "invalid_blocks",
        "invalid_arguments",
        "missing_scope",
        "not_authed",
        "invalid_auth",
        "account_inactive",
        "channel_not_found",
        "no_team",
    )

    def _retry_after_hint(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if isinstance(headers, dict):
            raw = headers.get("Retry-After") or headers.get("retry-after")
            if raw and str(raw).isdigit():
                return max(1, int(raw))
        msg = str(exc)
        m = re.search(r"retry(?:ing)? in (\d+)s", msg, re.I)
        if m:
            return max(1, int(m.group(1)))
        return None

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
            lower = str(e).lower()
            if any(marker in lower for marker in non_retryable_markers):
                break
            if attempt < max_retries - 1:
                wait = _retry_after_hint(e) or delays[min(attempt, len(delays) - 1)]
                safe_err = _sanitize_sensitive_text(str(e))
                print(
                    f"  {op_label} failed ({safe_err}); retrying in {wait}s "
                    f"[{attempt+1}/{max_retries}]"
                )
                time.sleep(wait)
                continue
    if dead_letter_payload is not None:
        _write_dead_letter(dead_letter_payload, str(last_err))
        print(f"  ❌ {op_label} failed after {max_retries} attempts; payload → {DEAD_LETTER}")
    raise last_err  # type: ignore[misc]


# ── Bot-token threaded helpers (Round 4) ─────────────────────────────────────

def _bot_client():
    """Build a slack_sdk WebClient from SLACK_BOT_TOKEN. Raises if missing."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token.startswith("xoxb-"):
        raise RuntimeError("SLACK_BOT_TOKEN (xoxb-...) required for threaded mode")
    from slack_sdk import WebClient
    return WebClient(token=token)


def _post_to_channel(
    blocks: list[dict],
    attachments: list[dict] | None = None,
    text_fallback: str = "Frontier Scout update",
    use_bot_identity: bool = True,
) -> str:
    """Post a top-level message to the configured channel. Returns ts.

    When `use_bot_identity` is True (default), the message renders with the
    'Frontier Scout' display name + satellite icon overrides. This requires the
    bot to have `chat:write.customize` scope; if missing, slack-sdk raises
    `not_authed`-class errors and we should fall back. For safety, the override
    is treated as a polish — failures fall through to the standard identity.
    """
    client = _bot_client()
    kwargs = dict(
        channel=os.environ["SLACK_CHANNEL_ID"],
        blocks=blocks,
        attachments=attachments,
        text=text_fallback,
        unfurl_links=False,
        unfurl_media=False,
    )
    if use_bot_identity:
        kwargs["username"] = BOT_DISPLAY_NAME
        kwargs["icon_emoji"] = BOT_ICON_EMOJI
    try:
        resp = client.chat_postMessage(**kwargs)
    except Exception as e:  # noqa: BLE001
        # If the identity override fails (e.g. missing chat:write.customize),
        # retry once without it.
        if use_bot_identity and "missing_scope" in str(e):
            kwargs.pop("username", None)
            kwargs.pop("icon_emoji", None)
            resp = client.chat_postMessage(**kwargs)
        else:
            raise
    return resp["ts"]


def _post_thread_reply(
    thread_ts: str,
    blocks: list[dict] | None = None,
    attachments: list[dict] | None = None,
    text_fallback: str = "Frontier Scout verdict",
) -> str:
    """Post a reply under thread_ts. Returns the new reply's ts."""
    client = _bot_client()
    resp = client.chat_postMessage(
        channel=os.environ["SLACK_CHANNEL_ID"],
        thread_ts=thread_ts,
        blocks=blocks,
        attachments=attachments,
        text=text_fallback,
        unfurl_links=False,
        unfurl_media=False,
    )
    return resp["ts"]


def _extract_slack_error(exc) -> str:
    """Extract the `error` field from a SlackApiError response.

    slack_sdk wraps API failures in SlackApiError, which has a `.response`
    attribute. The response carries the raw API payload — including the
    machine-readable `error` field (e.g. "missing_scope", "ratelimited",
    "already_reacted"). Falling back to the str(exc) representation loses
    that field behind a wall of formatted text.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    data = getattr(response, "data", None) or {}
    return data.get("error", "") if isinstance(data, dict) else ""


# Errors that mean "this and every subsequent reaction will fail the same
# way" — log once and bail rather than spamming the operator with 21 copies
# of the same root cause. Keeps CI logs readable when scopes are wrong or
# Slack is rate-limiting.
_REACTION_BAIL_ERRORS = {
    "missing_scope",       # bot wasn't reinstalled with reactions:write
    "not_authed",          # token wholly invalid
    "invalid_auth",        # token revoked / rotated
    "account_inactive",    # workspace or app disabled
    "ratelimited",         # Tier 3 cap (50/min) hit — backing off helps nobody mid-loop
}


# Module-level circuit breaker. If one card's reactions blow up with an
# unrecoverable error (missing_scope, not_authed, etc.), every subsequent
# card in the same briefing will hit the same wall — log it ONCE for the
# whole run and skip cleanly for the rest. reset_reaction_breaker() is
# called once per weekly_briefing_threaded() so the next run starts fresh.
_REACTION_BREAKER_TRIPPED: dict = {}


def reset_reaction_breaker() -> None:
    """Clear the cross-card circuit breaker. Called at the start of each
    threaded post so the state doesn't leak between independent runs."""
    _REACTION_BREAKER_TRIPPED.clear()


def _add_reactions(message_ts: str, emojis=DEFAULT_VERDICT_REACTIONS) -> None:
    """Bot adds reactions to its own message. Each failure is logged, not raised
    — auto-reactions are nice-to-have, not delivery-critical.

    Three failure classes:
      • `already_reacted` — silent continue (the bot's own retry path hit
        the same message twice; no operator signal needed)
      • scope/auth/ratelimit — log ONCE per run (module-level breaker)
        and skip every remaining card; the next briefing tries fresh
      • anything else — log per-emoji with the real Slack error code so the
        operator can act on it
    """
    # Circuit-breaker: silently skip if a previous card in this run already
    # hit an unrecoverable error. Avoids 21 identical log lines.
    if _REACTION_BREAKER_TRIPPED:
        return

    try:
        client = _bot_client()
    except RuntimeError as e:
        print(f"  Skipping reactions: {e}")
        return
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    for i, emoji in enumerate(emojis):
        try:
            client.reactions_add(channel=channel, timestamp=message_ts, name=emoji)
        except Exception as e:  # noqa: BLE001
            reason = _extract_slack_error(e)

            # Silent continue — the bot already put this emoji on this card.
            if reason == "already_reacted":
                continue

            # Unrecoverable for THIS run — log once via breaker; remaining
            # cards in this run will silently skip.
            if reason in _REACTION_BAIL_ERRORS:
                hint = {
                    "missing_scope": "reinstall the Slack app to grant `reactions:write`",
                    "not_authed": "SLACK_BOT_TOKEN is invalid — check Lambda env vars",
                    "invalid_auth": "SLACK_BOT_TOKEN was revoked — rotate and update env vars",
                    "account_inactive": "workspace or app is disabled",
                    "ratelimited": "Slack Tier 3 rate cap; will recover on the next briefing",
                }.get(reason, "")
                print(
                    f"  ⚠️  Skipping all reactions for this run — "
                    f"Slack returned {reason!r}. ({hint})"
                )
                _REACTION_BREAKER_TRIPPED[reason] = True
                return

            # Some other failure mode (e.g. invalid_name for a custom emoji
            # that doesn't exist in the workspace) — log the reason and try
            # the next emoji; other reactions on this card may still land.
            print(f"  reactions.add {emoji!r}: {reason or str(e)[:80]}")

        # Defensive: small spacing between reactions to stay below Slack's
        # Tier 3 cap (50/min). 100ms × 3 emojis × N cards is still under 1s
        # extra wall-clock per briefing, well worth avoiding the next bug.
        if i < len(emojis) - 1:
            time.sleep(0.1)


# ── Lab reply (Round 8) ──────────────────────────────────────────────────────
#
# Replaces the plain-text wall that lab_runner._format_reply produced before
# Round 8. Same skeleton as a verdict card so both surfaces speak one design
# dialect: attachment color carries the recommendation (red = skip,
# amber = trial, gray = monitor), recommendation pill sits in the FIRST
# block (not buried), *Worked* | *Didn't* renders as a two-column fields
# section, and the next-step gets isolated visual prominence.

_LAB_RECOMMENDATION_COLOR = {
    "worth_trial": "#f2c744",  # amber — matches the TRIAL tier on Scout verdict cards
    "monitor":     "#9aa0a6",  # gray  — matches ASSESS
    "skip":        "#d93025",  # red   — matches HOLD
}

_LAB_RECOMMENDATION_PILL = {
    "worth_trial": "🟡 worth a TRIAL",
    "monitor":     "⚪ MONITOR for now",
    "skip":        "🔴 SKIP",
}

_LAB_QUALITY_TRAIL = {
    "high":   ":white_check_mark: high-confidence test",
    "medium": ":large_blue_circle: medium-confidence test",
    "low":    ":warning: best-effort test (imports/smoke only)",
}


def lab_result_blocks(
    *,
    tool: str,
    url: str,
    classification: dict,
    sandbox: dict,
    insights: dict,
    cost: float,
    test_excerpt: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build (outer_blocks, attachments) for a lab reply, same skeleton as
    a verdict card. Returns an empty outer_blocks list because the lab
    reply has no interactive actions yet — everything lives inside the
    colored attachment.

    Round 8 redesign — see plan for the before/after comparison.
    """
    rec = (insights or {}).get("verdict_for_team", "monitor")
    color = _LAB_RECOMMENDATION_COLOR.get(rec, "#9aa0a6")
    pill = _LAB_RECOMMENDATION_PILL.get(rec, rec.upper())
    pkg = classification.get("package") or tool
    duration = float((sandbox or {}).get("duration_s", 0))
    exit_code = (sandbox or {}).get("exit_code", 0)
    stage = (sandbox or {}).get("stage", "run")
    quality = (insights or {}).get("test_quality_self_rating", "medium")

    # Hero section — bold linked tool + recommendation pill on one line,
    # italicized headline on a second line (same shape as verdict card hero).
    link = _safe_link(url, tool)
    headline = (insights or {}).get("headline", "").strip()
    hero_lines = [f"🧪  Lab: *{link}*  ·  {pill}"]
    if headline:
        hero_lines.append(f"_{headline}_")
    hero_block: dict = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(hero_lines)},
    }
    accessory = _image_accessory(url, classification.get("category", "tool"))
    if accessory is not None:
        hero_block["accessory"] = accessory

    # Metadata strip — exit status + duration + cost + test-quality badge.
    exit_label = (
        "✅ clean run" if exit_code == 0
        else f"❌ {stage} failed (exit {exit_code})"
    )
    meta_strip = (
        f"{exit_label}  ·  {duration:.0f}s  ·  ${cost:.3f}  ·  "
        f"{_LAB_QUALITY_TRAIL.get(quality, quality)}"
    )

    # Two-column fields — *Worked* | *Didn't*. Same layout as verdict
    # card's *Adoption* | *Next action*.
    worked = (insights or {}).get("what_worked", "").strip() or "—"
    didnt = (insights or {}).get("what_didnt", "").strip() or "—"
    fields_block = {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Worked*\n{worked}"},
            {"type": "mrkdwn", "text": f"*Didn't*\n{didnt}"},
        ],
    }

    inner_blocks: list[dict] = [
        hero_block,
        _context(meta_strip),
        fields_block,
    ]

    # Optional rich_text_preformatted code excerpt — proves the test
    # really ran by showing the actual script lines (Round 8 credibility
    # move). Only included when test_excerpt is non-empty.
    if test_excerpt and test_excerpt.strip():
        inner_blocks.append(_rich_text(_rt_preformatted(test_excerpt.strip())))

    # Next step gets a context-block-isolated last line. Bold-text label,
    # no emoji label.
    next_step = (insights or {}).get("next_step", "").strip()
    if next_step:
        inner_blocks.append(_context(f"*Next step* — {next_step}"))

    attachment = {
        "color": color,
        "blocks": inner_blocks,
        "fallback": f"Lab: {tool} — {pill.split(' ', 1)[-1]}",
    }
    return [], [attachment]


def quiet_week_blocks(
    *,
    date: str,
    scanned: int,
    dedup_drops: int = 0,
    prior_drops: int = 0,
    candidates: int = 0,
    reason: str,
    cost: float = 0.0,
    duration_s: float | None = None,
    detail: str = "",
) -> list[dict]:
    """Build a "quiet week" parent message for when the pipeline produced
    no verdicts. The bot ALWAYS posts something on its schedule — silence
    makes people assume the bot is broken. A short, honest heartbeat is
    the right signal: scanned N, considered M, shipped 0, here's why.

    `reason` is one of:
      - "fetch_empty"   — scanned=0; sources didn't return anything (likely
                          upstream flake or genuine quiet)
      - "all_filtered"  — every fetched item was a duplicate or already in
                          Mem0; the radar is up-to-date
      - "no_verdicts"   — items scored fine but judge+policy vetoed everything
                          OR the model rated all items below the threshold

    `detail` is an optional one-liner appended verbatim — useful for surfacing
    "arXiv timed out" or "max_tokens hit, possibly truncated."
    """
    headlines = {
        "fetch_empty": (
            ":new_moon:  *Lean fetch this week* — no items reached scoring. "
            "Sources may be quiet (holidays / between releases) or some "
            "upstream feeds flaked. Pipeline is healthy."
        ),
        "all_filtered": (
            ":dart:  *Radar already up-to-date* — every fetched item was "
            "either a duplicate or already evaluated in Mem0. Nothing new "
            "this cycle, by definition."
        ),
        "no_verdicts": (
            ":new_moon:  *Quiet week* — items were scanned and scored, but "
            "none rose above the verdict threshold or the judge cleared "
            "them all. Sources are healthy; nothing notable this cycle."
        ),
    }
    headline = headlines.get(reason, headlines["no_verdicts"])

    considered = max(0, scanned - dedup_drops - prior_drops)
    duration_str = f"  ·  ⏱ {int(duration_s)}s" if duration_s else ""

    blocks: list[dict] = [
        _header(f"📡  Frontier Scout — Weekly Briefing · {date}"),
        _section(headline),
        _context(
            f"*{scanned}* scanned  ·  *{considered}* considered  ·  *{candidates}* "
            "after Mem0 filter  ·  *0* shipped"
        ),
        _context(f"💰 ${cost:.4f}{duration_str}"),
    ]
    if detail:
        blocks.append(_context(f":information_source: {detail}"))
    blocks.append(_divider())
    blocks.append(_context(
        "No verdicts in thread this cycle. "
        "`/radar <tool>` to query prior verdicts  ·  "
        "`/recall <topic>` to search the radar."
    ))
    return blocks


def _tuned_by_line() -> str:
    """One-line summary of the channel taste model. Empty in cold start.

    Best-effort: any failure to load preferences.json returns "" so the
    briefing always posts even if the taste model is unavailable.
    """
    try:
        import preferences  # local import — keep slack_post importable in tests
        prefs = preferences.load()
    except Exception as e:  # noqa: BLE001
        print(f"  _tuned_by_line: preferences unavailable: {e}")
        return ""
    n = int(prefs.get("signal_count_14d", 0) or 0)
    if n < preferences.COLD_START_THRESHOLD:
        return ""
    reactions = int(prefs.get("reaction_count_14d", 0) or 0)
    labs = int(prefs.get("lab_count_14d", 0) or 0)
    if labs:
        return (
            f"📈  *Tuned by* `{reactions}` reactions + `{labs}` lab queues "
            f"over the last 14 days"
        )
    return f"📈  *Tuned by* `{reactions}` reactions over the last 14 days"


def _threaded_parent_blocks(
    date: str,
    scanned: int,
    cost: float,
    verdicts: list[dict],
    judge_rating: str,
    judge_summary: str,
    dedup_drops: int,
    prior_drops: int,
    duration_s: float | None = None,
) -> list[dict]:
    return _briefing_overview_blocks(
        date=date,
        scanned=scanned,
        cost=cost,
        verdicts=verdicts,
        judge_rating=judge_rating,
        judge_summary=judge_summary,
        dedup_drops=dedup_drops,
        prior_drops=prior_drops,
        duration_s=duration_s,
        top_k=_MAX_PARENT_HIGHLIGHTS,
    )


# Slack hard-caps overflow option `value` at 150 chars and rejects the
# entire `chat.postMessage` call with `invalid_blocks` if any option blows
# past it. The wider `action_context` blob (tool + verdict + soc2 + category
# + URL) easily clears 200 chars for real verdicts, which took down every
# thread reply in the 2026-05-21 live run.
#
# Buttons accept up to 2000 chars on `value` and keep the full context.
# Overflow options carry only what the dispatcher genuinely needs:
#   a = action id (mark_seen / snooze_30d / copy_link)
#   t = tool_name, truncated so the JSON stays under our internal cap
#
# For `copy_link`, the dispatcher resolves the URL from the latest briefing
# (already mirrored on the Lambda via `github_mirror`) — no need to
# round-trip it through Slack.
_MAX_OVERFLOW_VALUE = 140  # 10-char safety margin below Slack's 150-char limit

# Round 7: the 🧪 Run Lab button is only shown when the verdict's source
# URL points to a real open-source repo, so the lab runner can actually
# pull and exercise the tool. Closed-source / paywalled / blog-post URLs
# get the other action buttons but not the lab.
_OPEN_SOURCE_URL_RE = re.compile(
    r"^https?://(www\.)?(github\.com|pypi\.org|huggingface\.co|gitlab\.com)/",
    re.IGNORECASE,
)


def _is_open_source_url(url: str) -> bool:
    """True if `url` looks like an open-source repository the lab can pull."""
    if not isinstance(url, str):
        return False
    return bool(_OPEN_SOURCE_URL_RE.match(url))


def _overflow_value(action: str, tool: str) -> str:
    """Pack an overflow option value safely under the Slack length limit."""
    payload = {"a": action, "t": (tool or "")[:100]}
    val = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(val) > _MAX_OVERFLOW_VALUE:
        # Belt-and-braces — the [:100] cap should make this unreachable,
        # but if a future field is added we want a loud assert here, not
        # a silent invalid_blocks at runtime against Slack.
        spill = len(val) - _MAX_OVERFLOW_VALUE
        payload["t"] = (tool or "")[: max(20, 100 - spill)]
        val = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    assert len(val) <= _MAX_OVERFLOW_VALUE, (
        f"overflow value {len(val)} > {_MAX_OVERFLOW_VALUE} after truncation: {val!r}"
    )
    return val


def _threaded_verdict_card(
    num: int,
    v: dict,
    *,
    include_actions: bool = True,
    show_rank: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Build one verdict card. Supports actionless reuse for deep-eval replies."""
    url = v.get("source_url", "")
    tool_name = _clip(v.get("tool_name", "Tool"), 80)
    link = _safe_link(url, tool_name)
    what = _clip(v.get("what", ""), 220)
    why_matters = _clip(v.get("why_it_matters", ""), 420)
    why_now = _clip(v.get("why_this_week", ""), 220)
    readiness = int(v.get("readiness", 3))
    meter = _readiness_meter(readiness)
    sev_icon = SEVERITY_ICON.get(v.get("severity", "standard"), "📌")
    tier_word = VERDICT_LABEL.get(v.get("verdict", "assess"), "ASSESS")
    category_word = CATEGORY_LABEL.get(v.get("category", "tool"), "Tools & Frameworks")
    soc2_word = SOC2_LABEL.get(v.get("soc2", "conditional"), "SOC2-conditional")

    badge_line = f"{tier_word} · {(v.get('severity', 'standard') or 'standard').capitalize()} · {soc2_word}"
    rank_prefix = f"{_verdict_marker(num)}  " if show_rank else ""
    hero_lines = [
        f"{rank_prefix}*{link}*",
        f"{badge_line} · Readiness `{meter}` {readiness}/5",
    ]
    if what:
        hero_lines.append(f"_{_escape_mrkdwn(what)}_")

    hero_block: dict = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(hero_lines)},
    }
    accessory = _image_accessory(url, v.get("category", "tool"))
    if accessory is not None:
        hero_block["accessory"] = accessory

    why_block = _section(
        "*Why it matters*\n"
        f"{_escape_mrkdwn(why_matters or 'No impact rationale provided.')}"
    )
    fields_block = {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*Adoption cost*\n{_escape_mrkdwn(_clip(v.get('adoption_cost', '—'), 240))}"},
            {"type": "mrkdwn", "text": f"*Next action*\n{_escape_mrkdwn(_clip(v.get('next_action', '—'), 240))}"},
        ],
    }

    inner_blocks: list[dict] = [
        hero_block,
        why_block,
        fields_block,
    ]

    notes: list[str] = [f"Category {category_word}"]
    if why_now:
        notes.append(f"Why now: {why_now}")
    trend = _memory_trend_text(v.get("tool_name", ""), v.get("verdict", "assess"))
    if trend:
        notes.append(trend)
    if url and not domain_allowed(url):
        notes.append("Source link hidden (domain not allowlisted).")
    if notes:
        notes_line = " · ".join(_clip(n, _MAX_LINE_CHARS) for n in notes)
        inner_blocks.append(_context(_clip(notes_line, 320)))

    attachment = {
        "color": TIER_COLOR.get(v.get("verdict", "assess"), "#9aa0a6"),
        "blocks": inner_blocks,
        "fallback": _clip(
            f"{tool_name}: {tier_word} · {soc2_word} · next action {v.get('next_action', '')}",
            220,
        ),
    }

    if not include_actions:
        return [], [attachment]

    action_payload = {
        "tool_name": _clip(v.get("tool_name", ""), 120),
        "verdict": v.get("verdict", ""),
        "soc2": v.get("soc2", ""),
        "category": v.get("category", ""),
        "source_url": _clip(url, 1000),
    }
    action_context = json.dumps(action_payload, ensure_ascii=False)
    if len(action_context) > 1900:
        action_payload["source_url"] = _clip(url, 300)
        action_context = json.dumps(action_payload, ensure_ascii=False)
    tool_label = tool_name[:60]
    lab_button_visible = _is_open_source_url(url)
    lab_button = {
        "type": "button",
        "text": {"type": "plain_text", "text": "Run Lab", "emoji": True},
        "action_id": "verdict_lab",
        "value": action_context,
        "style": "primary",
        "accessibility_label": _a11y_label(
            f"Run automated lab on {tool_label} against your stack patterns"
        ),
    } if lab_button_visible else None

    outer_blocks: list[dict] = [{
        "type": "actions",
        "block_id": f"verdict_actions_{num}",
        "elements": [
            *([lab_button] if lab_button is not None else []),
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Deep Evaluation", "emoji": True},
                "action_id": "verdict_evaluate",
                "value": action_context,
                "accessibility_label": _a11y_label(f"Run full evaluation on {tool_label}"),
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Compare", "emoji": True},
                "action_id": "verdict_compare",
                "value": action_context,
                "accessibility_label": _a11y_label(
                    f"Compare current verdict on {tool_label} to prior verdicts"
                ),
            },
            {
                "type": "overflow",
                "action_id": "verdict_overflow",
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "Mark as evaluated", "emoji": True},
                        "value": _overflow_value("mark_seen", v.get("tool_name", "")),
                    },
                    {
                        "text": {"type": "plain_text", "text": "Snooze for 30 days", "emoji": True},
                        "value": _overflow_value("snooze_30d", v.get("tool_name", "")),
                    },
                    {
                        "text": {"type": "plain_text", "text": "Copy source link", "emoji": True},
                        "value": _overflow_value("copy_link", v.get("tool_name", "")),
                    },
                ],
            },
        ],
    }]
    return outer_blocks, [attachment]


def weekly_briefing_threaded(
    date: str,
    scanned: int,
    cost: float,
    verdicts: list[dict],
    judge_rating: str = "medium",
    judge_summary: str = "",
    dedup_drops: int = 0,
    prior_drops: int = 0,
    duration_s: float | None = None,
    add_reactions: bool = True,
) -> str | None:
    """Bot-token threaded format: parent TL;DR + per-verdict thread cards
    + auto-reactions on each card.

    Returns the parent message ts (or None in DRY_RUN).
    """
    # Clear the cross-card reaction breaker so a fresh run starts clean.
    # If a previous run hit missing_scope, that shouldn't carry over once
    # the operator has reinstalled the app.
    reset_reaction_breaker()

    parent_blocks = _threaded_parent_blocks(
        date=date,
        scanned=scanned,
        cost=cost,
        verdicts=verdicts,
        judge_rating=judge_rating,
        judge_summary=judge_summary,
        dedup_drops=dedup_drops,
        prior_drops=prior_drops,
        duration_s=duration_s,
    )

    if os.environ.get("DRY_RUN") == "1":
        print("─── SLACK DRY RUN (threaded · parent) ─────────────────")
        print(json.dumps(parent_blocks, indent=2, ensure_ascii=False))

    # Group verdicts by tier; sequential numbering follows the canonical
    # tier order so #1 is always the top ADOPT (or top TRIAL if no ADOPT, etc.)
    by_tier: dict[str, list[tuple[int, dict]]] = {t: [] for t in TIER_ORDER}
    counter = 0
    for tier in TIER_ORDER:
        for v in verdicts:
            if v["verdict"] == tier:
                counter += 1
                by_tier[tier].append((counter, v))

    if os.environ.get("DRY_RUN") == "1":
        for tier in TIER_ORDER:
            group = by_tier[tier]
            if not group:
                continue
            for num, v in group:
                outer, atts = _threaded_verdict_card(num, v)
                print(f"─── SLACK DRY RUN (threaded · #{num} {v['tool_name']}) ───")
                print(json.dumps({"blocks": outer, "attachments": atts}, indent=2, ensure_ascii=False))
                if add_reactions:
                    print(f"     would add reactions: {DEFAULT_VERDICT_REACTIONS}")
        print("─── END SLACK DRY RUN ─────────────────────────────────")
        return None

    # Real send: parent first. Track partial delivery so a parent-success +
    # thread-failure case is visible in quality-log.jsonl rather than silently
    # counting as a clean post.
    delivery: dict = {"parent": False, "anchors_attempted": 0, "anchors_failed": 0,
                      "verdicts_attempted": 0, "verdicts_failed": 0}
    # message_ts → verdict-card meta. Persisted to briefings/<date>-meta.json
    # so the Lambda reaction dispatcher can enrich incoming reactions with
    # {tool, category, tags} without having to grep the briefing markdown.
    ts_to_meta: dict[str, dict] = {}

    # Meaningful top-level `text` for accessibility + notification previews.
    # Screen readers + Slack's mobile notification banner use this when blocks
    # are present, so a generic "Frontier Scout update" was a real a11y miss.
    parent_fallback = (
        f"Frontier Scout weekly briefing for {date}: {len(verdicts)} verdicts "
        f"from {scanned} scanned items, judge confidence {judge_rating}."
    )
    parent_ts = _with_slack_retry(
        _post_to_channel,
        parent_blocks,
        op_label="slack parent",
        dead_letter_payload={"blocks": parent_blocks},
        text_fallback=parent_fallback,
    )
    delivery["parent"] = True

    # Post each verdict card in tier order.
    for tier in TIER_ORDER:
        group = by_tier[tier]
        if not group:
            continue
        for num, v in group:
            outer, atts = _threaded_verdict_card(num, v)
            # Per-card fallback names the tool + verdict so push notifications
            # and screen readers carry real meaning, not "Frontier Scout verdict".
            card_fallback = (
                f"#{num} {v['tool_name']}: {v['verdict'].upper()} · "
                f"{v.get('category', 'tool')} · SOC2-{v.get('soc2', '?')} · "
                f"next: {_clip(v.get('next_action', ''), 70)}"
            )
            delivery["verdicts_attempted"] += 1
            try:
                reply_ts = _with_slack_retry(
                    _post_thread_reply,
                    parent_ts,
                    outer,                      # actions block (interactive)
                    atts,                       # colored card (read-only)
                    op_label=f"slack thread #{num}",
                    dead_letter_payload={"thread_ts": parent_ts, "blocks": outer, "attachments": atts},
                    text_fallback=card_fallback,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  verdict #{num} thread reply failed permanently: {e}")
                delivery["verdicts_failed"] += 1
                continue
            if add_reactions:
                _add_reactions(reply_ts)
            if reply_ts:
                ts_to_meta[reply_ts] = {
                    "tool": v["tool_name"],
                    "category": v.get("category", ""),
                    "tags": [t.lower() for t in (v.get("tags") or [])],
                    "verdict": v.get("verdict", ""),
                    "soc2": v.get("soc2", ""),
                    "num": num,
                }

    if delivery["verdicts_failed"] > 0:
        failure_blocks = [
            _section(
                ":warning: Some verdict cards could not be posted.\n"
                f"{delivery['verdicts_failed']} of {delivery['verdicts_attempted']} failed. "
                "The run summary is valid; check pipeline logs before sharing."
            ),
        ]
        try:
            _with_slack_retry(
                _post_thread_reply,
                parent_ts,
                failure_blocks,
                None,
                op_label="slack thread failure notice",
                dead_letter_payload={"thread_ts": parent_ts, "blocks": failure_blocks},
                text_fallback="Frontier Scout warning: some verdict cards failed to post.",
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  failed to post thread failure notice: {e}")

    # Persist the message_ts → meta map for the reaction dispatcher. Lives
    # under briefings/ so it's committed alongside the briefing markdown
    # (existing pipeline step `git add briefings/` picks it up automatically).
    if ts_to_meta:
        try:
            meta_path = BRIEFINGS_DIR / f"{date}-meta.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(
                {"parent_ts": parent_ts, "verdicts": ts_to_meta},
                indent=2, sort_keys=True,
            ) + "\n")
            print(f"  📝 wrote {meta_path.name} ({len(ts_to_meta)} cards mapped)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  failed to write briefing meta: {e}")

    # Surface partial-delivery state to the caller via a module-level dict.
    # Scout reads this after the call and writes it into quality-log.jsonl.
    global LAST_DELIVERY
    LAST_DELIVERY = delivery
    if delivery["verdicts_failed"] or delivery["anchors_failed"]:
        print(
            f"  ⚠️  partial delivery: "
            f"verdicts {delivery['verdicts_failed']}/{delivery['verdicts_attempted']} failed, "
            f"anchors {delivery['anchors_failed']}/{delivery['anchors_attempted']} failed"
        )
    return parent_ts


# Module-level dict captures the most recent threaded-delivery outcome so the
# pipeline can record partial-delivery state in quality-log.jsonl.
LAST_DELIVERY: dict = {}


def _tier_anchor_text(tier: str, count: int) -> str:
    """Render the tier-anchor reply text shown between tier groups in thread.

    Slack threads already get natural visual separation from reply boundaries;
    keep the anchor lightweight so it reads as a section label, not a heavy rule.
    """
    tier_emoji = VERDICT_EMOJI[tier]
    plural = "verdict" if count == 1 else "verdicts"
    return f"*{tier_emoji}*  ·  {count} {plural}"


def post(blocks: list[dict], thread_ts: str | None = None, max_retries: int = 3) -> str | None:
    """
    Post blocks to the configured Slack target with retry + dead letter.

    Auth (auto-detected in order):
      1. SLACK_WEBHOOK_URL — Incoming Webhook
      2. SLACK_BOT_TOKEN containing https://hooks.slack.com/... — auto-route
      3. SLACK_BOT_TOKEN (xoxb-) + SLACK_CHANNEL_ID — bot mode

    DRY_RUN=1: print payload, don't send.

    Retries with exponential backoff (1s → 4s → 16s). If all retries fail,
    writes payload to .scratch/slack-dead-letter.jsonl and re-raises the
    last exception. The dead letter is committed by the pipeline so the
    operator can inspect and re-post.
    """
    if os.environ.get("DRY_RUN") == "1":
        print("─── SLACK DRY RUN ──────────────────────────────────")
        print(json.dumps(blocks, indent=2, ensure_ascii=False))
        print("─── END SLACK DRY RUN ──────────────────────────────")
        return None

    return _with_slack_retry(
        _do_post,
        blocks,
        thread_ts,
        max_retries=max_retries,
        dead_letter_payload={"blocks": blocks, "thread_ts": thread_ts},
        op_label="slack post",
    )
