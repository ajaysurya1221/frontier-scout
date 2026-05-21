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
        _header(f"📡 Frontier Scout — Weekly Briefing · {date}"),
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
        _header(f"📊 Frontier Scout — Monthly Synthesis · {month}"),
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
            f"{alert}*Frontier Scout — Cost Report*\n"
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
    """Build the channel-visible parent message blocks: header + funnel +
    judge's read + numbered TL;DR scanner grouped by tier."""
    sev_counts = {"critical": 0, "high": 0, "standard": 0}
    for v in verdicts:
        sev_counts[v.get("severity", "standard")] = sev_counts.get(v.get("severity", "standard"), 0) + 1

    considered = scanned - dedup_drops - prior_drops
    duration_str = f" · ⏱ {int(duration_s)}s" if duration_s else ""

    blocks: list[dict] = [
        _header(f"📡  Frontier Scout — Weekly Briefing · {date}"),
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

    # "Tuned by N reactions" — channel taste model badge. Only shown above
    # the cold-start threshold so the team learns about it once it actually
    # influences rankings, not before.
    tuned_line = _tuned_by_line()
    if tuned_line:
        blocks.append(_context(tuned_line))

    blocks.append(_divider())
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": "TL;DR", "emoji": True},
    })

    # Group by tier and number sequentially.
    grouped: dict[str, list[tuple[int, dict]]] = {t: [] for t in TIER_ORDER}
    counter = 0
    for tier in TIER_ORDER:
        for v in verdicts:
            if v["verdict"] == tier:
                counter += 1
                grouped[tier].append((counter, v))

    # Two blocks per non-empty tier:
    #   1. Context block — colored emoji + tier label + count. Slack renders
    #      emojis inside context at ~14px instead of section's ~22px, so the
    #      colored circles stop dominating the layout.
    #   2. Section block — verdict rows with `#N` inline-code pills and
    #      bolded tool names. Tool name is the anchor; the index is a
    #      quiet reference handle.
    # No inter-tier dividers — context's smaller padding + section's natural
    # spacing already separate the groups cleanly.
    # Severity / category / SOC2 stay in the full verdict cards in the
    # thread — repeating them here would turn the TL;DR back into a wall
    # of symbols instead of a scanner.
    for tier in TIER_ORDER:
        items = grouped.get(tier, [])
        if not items:
            continue
        count = len(items)
        verdicts_word = "verdict" if count == 1 else "verdicts"
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*{VERDICT_EMOJI[tier]}*  ·  {count} {verdicts_word}",
                }
            ],
        })
        rows = [
            f"  {_verdict_marker(num)}   *{v['tool_name']}*"
            for num, v in items
        ]
        blocks.append(_section("\n".join(rows)))

    blocks.append(_divider())
    blocks.append(_context(
        "🧵  Full verdicts in thread  ·  🧪 lab  ·  👍 worth it  ·  👎 skip  "
        "·  `/radar <tool>`  ·  `/recall <topic>`"
    ))
    return blocks


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

    # Interactive components MUST live in the top-level `blocks` array — Slack
    # silently drops `actions` blocks placed inside attachments. Card content
    # stays in the attachment (so the tier-colored vertical bar still
    # renders); actions + overflow menu go in `outer_blocks` below.
    action_context = json.dumps({
        "tool_name": v["tool_name"],
        "verdict": v["verdict"],
        "soc2": v["soc2"],
        "category": v["category"],
        "source_url": v["source_url"],
    })

    attachment = {
        "color": TIER_COLOR.get(v["verdict"], "#9aa0a6"),
        "blocks": inner_blocks,
        "fallback": f"{v['tool_name']} — {v['verdict'].upper()}",
    }
    # `accessibility_label` is what Slack reads out to screen-reader users
    # instead of the visible button text. Visible labels carry emoji for the
    # sighted UI; the a11y label spells out the action plus the tool name so
    # the user knows *what* the action will affect, not just "queue lab."
    tool_label = v["tool_name"][:60]  # Slack caps a11y label at ~70 chars

    # Round 7: the 🧪 button only appears when the verdict's source URL is
    # an actually-open-source repository. Closed-source / vendor / paywalled
    # tools simply don't get a lab button — the runner can't pull them, and
    # surfacing a button that always fails would confuse operators.
    lab_button_visible = _is_open_source_url(v.get("source_url", ""))
    lab_button = {
        "type": "button",
        "text": {"type": "plain_text", "text": "🧪  Run Lab", "emoji": True},
        "action_id": "verdict_lab",
        "value": action_context,
        "style": "primary",
        "accessibility_label": f"Run automated lab on {tool_label} against configured stack patterns",
    } if lab_button_visible else None

    outer_blocks: list[dict] = [
        {
            "type": "actions",
            "block_id": f"verdict_actions_{num}",
            "elements": [
                *([lab_button] if lab_button is not None else []),
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📚  Full evaluation", "emoji": True},
                    "action_id": "verdict_evaluate",
                    "value": action_context,
                    "accessibility_label": f"Run full evaluation on {tool_label}",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📊  Compare", "emoji": True},
                    "action_id": "verdict_compare",
                    "value": action_context,
                    "accessibility_label": f"Compare current verdict on {tool_label} to prior verdicts",
                },
                {
                    # Three-dot overflow menu for secondary actions. Keeps the
                    # primary row uncluttered while exposing follow-ups that
                    # become useful as the radar accumulates Mem0 history.
                    "type": "overflow",
                    "action_id": "verdict_overflow",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "✓ Mark as already evaluated", "emoji": True},
                            "value": _overflow_value("mark_seen", v["tool_name"]),
                        },
                        {
                            "text": {"type": "plain_text", "text": "🔕 Snooze this tool 30 days", "emoji": True},
                            "value": _overflow_value("snooze_30d", v["tool_name"]),
                        },
                        {
                            "text": {"type": "plain_text", "text": "🔗 Copy source link", "emoji": True},
                            "value": _overflow_value("copy_link", v["tool_name"]),
                        },
                    ],
                },
            ],
        },
    ]
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
            print(f"─── SLACK DRY RUN (thread anchor · {tier.upper()}) ───")
            print(_tier_anchor_text(tier, len(group)))
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

    # Then, for each tier with verdicts, post a tier-anchor reply followed by
    # one colored attachment per verdict.
    for tier in TIER_ORDER:
        group = by_tier[tier]
        if not group:
            continue
        anchor_blocks = [_section(_tier_anchor_text(tier, len(group)))]
        anchor_fallback = f"{tier.upper()} tier — {len(group)} verdicts"
        delivery["anchors_attempted"] += 1
        try:
            _with_slack_retry(
                _post_thread_reply,
                parent_ts,
                anchor_blocks,
                None,
                op_label=f"slack tier-anchor {tier}",
                dead_letter_payload={"thread_ts": parent_ts, "blocks": anchor_blocks},
                text_fallback=anchor_fallback,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  tier anchor {tier} failed (continuing): {e}")
            delivery["anchors_failed"] += 1

        for num, v in group:
            outer, atts = _threaded_verdict_card(num, v)
            # Per-card fallback names the tool + verdict so push notifications
            # and screen readers carry real meaning, not "Frontier Scout verdict".
            card_fallback = (
                f"#{num} {v['tool_name']}: {v['verdict'].upper()} · "
                f"{v.get('category', 'tool')} · SOC2-{v.get('soc2', '?')}"
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
