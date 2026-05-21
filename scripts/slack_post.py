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
import time
from datetime import datetime, timezone
from pathlib import Path

from validators import domain_allowed

DEAD_LETTER = Path(__file__).parent.parent / ".scratch" / "slack-dead-letter.jsonl"

CATEGORY_EMOJI = {
    "frontier_model": "🧠 Frontier Models",
    "orchestration":  "🤖 Orchestration",
    "tool":           "🛠️ Tools & Frameworks",
    "data":           "📊 Data Ecosystem",
    "compute":        "⚡ Compute & Hardware",
    "security":       "🔐 Security & Compliance",
}

VERDICT_EMOJI = {
    "adopt":  "🟢 ADOPT",
    "trial":  "🟡 TRIAL",
    "assess": "⚪ ASSESS",
    "hold":   "🔴 HOLD",
}

SOC2_BADGE = {
    "safe":        "✅ SOC2-safe",
    "conditional": "⚠️ SOC2-conditional",
    "blocked":     "❌ SOC2-blocked",
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
# "AI Telemetry 📡" instead of the generic Slack-app name, with a satellite
# icon. Subtle but the system feels more like a product than a script.
BOT_DISPLAY_NAME = "AI Telemetry"
BOT_ICON_EMOJI = ":satellite_antenna:"

# Keycap emojis for the TL;DR scanner. Index 0 unused; positions 1-10 are
# rendered as the distinctive boxed digits. >10 falls back to "#N".
_KEYCAPS = [
    "",  # index 0 — never used
    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣",
    "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟",
]


def _verdict_marker(n: int) -> str:
    """Display marker for the Nth verdict — keycap for 1-10, '#N' beyond."""
    if 1 <= n <= 10:
        return _KEYCAPS[n]
    return f"*#{n}*"

JUDGE_CONFIDENCE = {
    "high":   "🤖 judge confidence: *HIGH*",
    "medium": "🤖 judge confidence: *medium*",
    "low":    "🤖 judge confidence: *low* — review before sharing",
}


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


def _safe_link(url: str, text: str) -> str:
    """Render a Slack hyperlink only if the URL's domain is in the allowlist.

    Untrusted/unknown domains fall back to bold text with the bare URL appended
    so the reader can still see where the link would have gone (and forensically
    review later) without risking a clickable redirect to a malicious target.
    """
    if not url:
        return f"*{text}*"
    if domain_allowed(url):
        return f"<{url}|{text}>"
    return f"*{text}* (link withheld: untrusted domain — `{url[:80]}`)"


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
    """
    Build Slack blocks for the Monday Weekly Briefing.

    `verdicts` items may include optional fields injected by the judge:
      - severity: "critical" | "high" | "standard"
      - readiness: 0..5
    """
    sev_counts = {"critical": 0, "high": 0, "standard": 0}
    for v in verdicts:
        sev_counts[v.get("severity", "standard")] = sev_counts.get(v.get("severity", "standard"), 0) + 1

    funnel = f"*{scanned}* scanned"
    if dedup_drops:
        funnel += f" → *{scanned - dedup_drops}* unique"
    if prior_drops:
        funnel += f" → *{scanned - dedup_drops - prior_drops}* fresh"
    funnel += f" → *{len(verdicts)}* verdicts"

    sev_line = (
        f"🔥 *{sev_counts.get('critical', 0)}* critical · "
        f"⭐ *{sev_counts.get('high', 0)}* high · "
        f"📌 *{sev_counts.get('standard', 0)}* standard"
    )

    blocks: list[dict] = [
        _header(f"📡 AI Telemetry — Weekly Briefing · {date}"),
        _context(f"{funnel}  ·  {JUDGE_CONFIDENCE.get(judge_rating, '')}  ·  💰 ${cost:.4f}"),
        _context(sev_line),
    ]
    if judge_summary:
        blocks.append(_section(f"🧠 _Judge's read:_ {judge_summary}"))
    blocks.append(_divider())

    # Group verdicts by tier in the canonical order
    tier_order = ["adopt", "trial", "assess", "hold"]
    grouped: dict[str, list[dict]] = {t: [] for t in tier_order}
    for v in verdicts:
        grouped.setdefault(v["verdict"], []).append(v)

    for tier in tier_order:
        items = grouped.get(tier, [])
        if not items:
            continue
        blocks.append(_section(f"*{TIER_HEADER[tier]}*"))
        for v in items:
            sev = v.get("severity", "standard")
            sev_icon = SEVERITY_ICON.get(sev, "📌")
            readiness = v.get("readiness", 3)
            meter = _readiness_meter(readiness)
            link = _safe_link(v["source_url"], v["tool_name"])
            body = (
                f"{sev_icon}  {link}  "
                f"·  {CATEGORY_EMOJI[v['category']]}  ·  {SOC2_BADGE[v['soc2']]}\n"
                f"_{v['what']}_\n"
                f"💡 {v['why_it_matters']}\n"
                f"⏱ *Adoption*: {v['adoption_cost']}\n"
                f"▶ *Next*: {v['next_action']}\n"
                f"📊 Readiness: `{meter}` {readiness}/5"
            )
            blocks.append(_section(body))
        blocks.append(_divider())

    blocks.append(_context("🧪 react to any verdict to queue a lab  ·  💭 reply in thread to discuss"))
    blocks.append(_context("`evaluate <tool>`  ·  `lab <tool>`  ·  `recall <topic>`"))
    return blocks


def pulse_blocks(
    source: str,
    title: str,
    url: str,
    when: str,
    verdict: dict | None = None,
) -> list[dict]:
    """
    Build Slack blocks for a Tier-S Pulse alert.

    If `verdict` is provided (from the judge pass), render the full verdict card.
    Otherwise just announce the drop with the standard reaction prompt.
    """
    blocks = [
        _section(f"*⚡ Tier-S Drop · {source}*  ·  _{when}_"),
        _section(_safe_link(url, title)),
    ]
    if verdict:
        sev = verdict.get("severity", "high")
        sev_icon = SEVERITY_ICON.get(sev, "⭐")
        readiness = verdict.get("readiness", 3)
        meter = _readiness_meter(readiness)
        blocks.append(_section(
            f"{sev_icon}  {VERDICT_EMOJI[verdict['verdict']]}  ·  "
            f"{CATEGORY_EMOJI[verdict['category']]}  ·  {SOC2_BADGE[verdict['soc2']]}\n"
            f"💡 {verdict['why_it_matters']}\n"
            f"▶ *Next*: {verdict['next_action']}\n"
            f"📊 Readiness: `{meter}` {readiness}/5"
        ))
    blocks.append(_context("React: 👍 worth my time  ·  👎 skip  ·  🧪 lab it"))
    return blocks


def synth_blocks(month: str, synthesis: dict) -> list[dict]:
    """Build Slack blocks for the monthly synthesis."""
    focus = synthesis["focus_this_month"]
    return [
        _header(f"📊 AI Telemetry — Monthly Synthesis · {month}"),
        _section(f"*What you've been exploring*\n{synthesis['exploration_summary']}"),
        _divider(),
        _section(
            "*Momentum check*\n"
            f"• *Adopted*: {', '.join(synthesis['adopted']) or '_nothing yet_'}\n"
            f"• *Stalled*: {', '.join(synthesis['stalled']) or '_none_'}\n"
            f"• *Blind spots*: {', '.join(synthesis['blind_spots']) or '_none_'}"
        ),
        _divider(),
        _section(
            f"*Focus this month: {focus['tool']}*\n"
            f"{focus['rationale']}\n"
            f"🧪 _Lab suggestion_: {focus['lab_suggestion']}"
        ),
        _divider(),
        _section(f"*Org opportunity*\n{synthesis['org_opportunity']}"),
    ]


def cost_report_blocks(month: str, mtd: float, limit: float = 10.0) -> list[dict]:
    pct = (mtd / limit) * 100 if limit else 0
    alert = "🚨 " if mtd > limit * 0.5 else "💰 "
    return [
        _section(
            f"{alert}*AI Telemetry — Cost Report*\n"
            f"_{month}_ spend: *${mtd:.4f}* / ${limit:.2f} limit  (`{pct:.1f}%`)"
        ),
    ]


def _write_dead_letter(blocks: list[dict], err: str) -> None:
    """Append the failed payload to .scratch/slack-dead-letter.jsonl."""
    DEAD_LETTER.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "error": str(err)[:500],
        "blocks": blocks,
    }
    with DEAD_LETTER.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _do_post(blocks: list[dict], thread_ts: str | None) -> str | None:
    """One attempt at posting. Raises on failure."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not webhook_url and bot_token.startswith("https://hooks.slack.com/"):
        webhook_url = bot_token
        bot_token = ""

    if webhook_url:
        import requests
        payload: dict = {"blocks": blocks, "text": "AI Telemetry update"}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return None  # webhooks don't return a ts

    if not bot_token:
        raise RuntimeError(
            "No Slack credentials. Set SLACK_WEBHOOK_URL (recommended) "
            "or SLACK_BOT_TOKEN + SLACK_CHANNEL_ID."
        )

    from slack_sdk import WebClient
    client = WebClient(token=bot_token)
    resp = client.chat_postMessage(
        channel=os.environ["SLACK_CHANNEL_ID"],
        blocks=blocks,
        thread_ts=thread_ts,
        text="AI Telemetry update",  # fallback for notifications
    )
    return resp["ts"]


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
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < max_retries - 1:
                wait = delays[min(attempt, len(delays) - 1)]
                print(
                    f"  {op_label} failed ({e!s}); retrying in {wait}s "
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
    text_fallback: str = "AI Telemetry update",
    use_bot_identity: bool = True,
) -> str:
    """Post a top-level message to the configured channel. Returns ts.

    When `use_bot_identity` is True (default), the message renders with the
    'AI Telemetry' display name + satellite icon overrides. This requires the
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
    text_fallback: str = "AI Telemetry verdict",
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


def _add_reactions(message_ts: str, emojis=DEFAULT_VERDICT_REACTIONS) -> None:
    """Bot adds reactions to its own message. Each failure is logged, not raised
    — auto-reactions are nice-to-have, not delivery-critical. Common benign
    failures: `already_reacted`, `invalid_name` (custom emoji absent), and
    `missing_scope` if the bot wasn't reinstalled with `reactions:write`."""
    try:
        client = _bot_client()
    except RuntimeError as e:
        print(f"  Skipping reactions: {e}")
        return
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    for emoji in emojis:
        try:
            client.reactions_add(channel=channel, timestamp=message_ts, name=emoji)
        except Exception as e:  # noqa: BLE001
            # Most reactions failures are non-fatal (already_reacted, etc.)
            msg = str(e)
            if "already_reacted" in msg:
                continue
            print(f"  reactions.add {emoji!r}: {msg[:120]}")


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
    """Build the channel-visible parent message blocks: header + funnel +
    judge's read + numbered TL;DR scanner grouped by tier."""
    sev_counts = {"critical": 0, "high": 0, "standard": 0}
    for v in verdicts:
        sev_counts[v.get("severity", "standard")] = sev_counts.get(v.get("severity", "standard"), 0) + 1

    considered = scanned - dedup_drops - prior_drops
    duration_str = f" · ⏱ {int(duration_s)}s" if duration_s else ""

    blocks: list[dict] = [
        _header(f"📡  AI Telemetry — Weekly Briefing · {date}"),
        _context(
            f"*{scanned}* scanned  ·  *{considered}* considered  ·  *{len(verdicts)}* shipped"
        ),
        _context(
            f"{JUDGE_CONFIDENCE.get(judge_rating, '')}  ·  💰 ${cost:.4f}{duration_str}"
        ),
        _context(
            f"🔥 *{sev_counts['critical']}* critical  ·  ⭐ *{sev_counts['high']}* high  ·  "
            f"📌 *{sev_counts['standard']}* standard"
        ),
    ]
    if judge_summary:
        blocks.append(_divider())
        blocks.append(_section(f"🧠  *Judge's read*\n> {judge_summary}"))

    blocks.append(_divider())
    blocks.append(_section("━━━━━━━━━━  *TL;DR*  ━━━━━━━━━━"))

    # Group by tier and number sequentially
    grouped: dict[str, list[tuple[int, dict]]] = {t: [] for t in TIER_ORDER}
    counter = 0
    for tier in TIER_ORDER:
        for v in verdicts:
            if v["verdict"] == tier:
                counter += 1
                grouped[tier].append((counter, v))

    for tier in TIER_ORDER:
        items = grouped.get(tier, [])
        if not items:
            continue
        lines = [f"*{VERDICT_EMOJI[tier]}*  ·  *{len(items)}*"]
        for num, v in items:
            sev_icon = SEVERITY_ICON.get(v.get("severity", "standard"), "📌")
            cat_short = CATEGORY_EMOJI[v["category"]].split(" ", 1)[0]
            soc2_short = SOC2_BADGE[v["soc2"]].split(" ", 1)[0]
            lines.append(
                f"  {_verdict_marker(num)}  {sev_icon}  *{v['tool_name']}*  "
                f"·  {cat_short}  ·  {soc2_short}"
            )
        blocks.append(_section("\n".join(lines)))

    blocks.append(_divider())
    blocks.append(_context(
        "🧵  Full verdicts in thread  →  react 🧪 to lab  ·  👍 worth it  ·  👎 skip"
    ))
    blocks.append(_context(
        "`evaluate <tool>`  ·  `lab <tool>`  ·  `recall <topic>`"
    ))
    return blocks


def _threaded_verdict_card(num: int, v: dict) -> tuple[list[dict], list[dict]]:
    """Build (blocks, attachments) for one verdict card in the thread.

    Blocks go inside an attachment so we get the colored vertical bar matching
    the tier (Slack's only mechanism for tier-color today).
    """
    sev_icon = SEVERITY_ICON.get(v.get("severity", "standard"), "📌")
    readiness = int(v.get("readiness", 3))
    meter = _readiness_meter(readiness)
    link = _safe_link(v["source_url"], v["tool_name"])

    header_text = f"{_verdict_marker(num)}  ·  {sev_icon}  {link}"
    badges = (
        f"{VERDICT_EMOJI[v['verdict']]}  ·  "
        f"{CATEGORY_EMOJI[v['category']]}  ·  {SOC2_BADGE[v['soc2']]}"
    )

    inner_blocks: list[dict] = [
        _section(header_text),
        _context(badges),
        _section(f"_{v['what']}_"),
        _section(f"💡  *Why it matters*\n{v['why_it_matters']}"),
    ]

    why_now = (v.get("why_this_week") or "").strip()
    if why_now:
        inner_blocks.append(_section(f"📅  *Why this week*\n> {why_now}"))

    # Two-column field layout for adoption cost + next action
    inner_blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"⏱  *Adoption*\n{v['adoption_cost']}"},
            {"type": "mrkdwn", "text": f"▶  *Next action*\n{v['next_action']}"},
        ],
    })

    inner_blocks.append(_context(f"📊  Readiness  `{meter}`  *{readiness}/5*"))

    # Interactive buttons — handled by the AWS Lambda backend if configured.
    # The `value` JSON blob carries the verdict context the Lambda needs,
    # avoiding a round-trip to look it up from the briefing message.
    action_context = json.dumps({
        "tool_name": v["tool_name"],
        "verdict": v["verdict"],
        "soc2": v["soc2"],
        "category": v["category"],
        "source_url": v["source_url"],
    })
    inner_blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🧪  Queue lab", "emoji": True},
                "action_id": "verdict_lab",
                "value": action_context,
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📚  Full evaluation", "emoji": True},
                "action_id": "verdict_evaluate",
                "value": action_context,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📊  Compare", "emoji": True},
                "action_id": "verdict_compare",
                "value": action_context,
            },
        ],
    })

    attachment = {
        "color": TIER_COLOR.get(v["verdict"], "#9aa0a6"),
        "blocks": inner_blocks,
        "fallback": f"{v['tool_name']} — {v['verdict'].upper()}",
    }
    # The parent message has no top-level blocks; everything lives in the
    # colored attachment for the bar to render correctly.
    return [], [attachment]


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
            print(f"─── SLACK DRY RUN (thread anchor · {tier.upper()}) ───")
            print(_tier_anchor_text(tier, len(group)))
            for num, v in group:
                _, atts = _threaded_verdict_card(num, v)
                print(f"─── SLACK DRY RUN (threaded · #{num} {v['tool_name']}) ───")
                print(json.dumps(atts, indent=2, ensure_ascii=False))
                if add_reactions:
                    print(f"     would add reactions: {DEFAULT_VERDICT_REACTIONS}")
        print("─── END SLACK DRY RUN ─────────────────────────────────")
        return None

    # Real send: parent first. Track partial delivery so a parent-success +
    # thread-failure case is visible in quality-log.jsonl rather than silently
    # counting as a clean post.
    delivery: dict = {"parent": False, "anchors_attempted": 0, "anchors_failed": 0,
                       "verdicts_attempted": 0, "verdicts_failed": 0}
    parent_ts = _with_slack_retry(
        _post_to_channel,
        parent_blocks,
        op_label="slack parent",
        dead_letter_payload={"blocks": parent_blocks},
    )
    delivery["parent"] = True

    # Then, for each tier with verdicts, post a tier-anchor reply followed by
    # one colored attachment per verdict.
    for tier in TIER_ORDER:
        group = by_tier[tier]
        if not group:
            continue
        anchor_blocks = [_section(_tier_anchor_text(tier, len(group)))]
        delivery["anchors_attempted"] += 1
        try:
            _with_slack_retry(
                _post_thread_reply,
                parent_ts,
                anchor_blocks,
                None,
                op_label=f"slack tier-anchor {tier}",
                dead_letter_payload={"thread_ts": parent_ts, "blocks": anchor_blocks},
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  tier anchor {tier} failed (continuing): {e}")
            delivery["anchors_failed"] += 1

        for num, v in group:
            _, atts = _threaded_verdict_card(num, v)
            delivery["verdicts_attempted"] += 1
            try:
                reply_ts = _with_slack_retry(
                    _post_thread_reply,
                    parent_ts,
                    None,                       # attachment owns rendering
                    atts,
                    op_label=f"slack thread #{num}",
                    dead_letter_payload={"thread_ts": parent_ts, "attachments": atts},
                )
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  verdict #{num} thread reply failed permanently: {e}")
                delivery["verdicts_failed"] += 1
                continue
            if add_reactions:
                _add_reactions(reply_ts)

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
    """Render the tier-anchor reply text shown between tier groups in thread."""
    tier_emoji = VERDICT_EMOJI[tier]
    return f"━━━━━━━━━━  *{tier_emoji}*  ·  *{count}*  ━━━━━━━━━━"


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
