"""
Reaction & thread-reply dispatcher — handles Slack `event_callback` payloads.

Subscribed events (set in the Slack app dashboard → Event Subscriptions):
  • reaction_added       — 👍 / 👎 / 🧪 etc. on a verdict card
  • reaction_removed     — undoing one of the above
  • message.channels     — thread replies on bot messages (signal of engagement)

For each event, we:
  1. Look up the message_ts in the latest briefings/<date>-meta.json (mirror)
     to enrich with {tool, category, tags, verdict, soc2}.
  2. Map the event to a canonical signal name (see SIGNAL_FROM_EMOJI).
  3. Append one line to signals-log.jsonl via GitHub REST (signal_log.py).

If the message_ts isn't in the meta (e.g. reactions on non-bot messages, or
on cards posted before this lands), we drop the signal silently — no point
spamming the ledger with anonymous noise.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import signal_log
import radar_query

# Slack reaction `name` → our canonical signal label. Keep in sync with
# SIGNAL_WEIGHTS in scripts/preferences.py.
SIGNAL_FROM_EMOJI: dict[str, str] = {
    "thumbsup":         "reaction_thumbsup",
    "+1":               "reaction_thumbsup",  # Slack alias
    "thumbsdown":       "reaction_thumbsdown",
    "-1":               "reaction_thumbsdown",
    "test_tube":        "reaction_test_tube",
}


def handle(body: dict) -> dict:
    """Dispatch an `event_callback` payload.

    Slack envelope:
      {"type": "event_callback", "event": {...}, "team_id": ..., ...}
    """
    event = body.get("event") or {}
    etype = event.get("type")

    if etype in {"reaction_added", "reaction_removed"}:
        return _handle_reaction(event, removed=(etype == "reaction_removed"))

    if etype == "message" and event.get("thread_ts") and not event.get("bot_id"):
        # A user replied in a thread on one of our bot messages
        return _handle_thread_reply(event)

    # Other subscribed events (none today) — ack so Slack doesn't retry
    return _ack()


# ── Reactions ────────────────────────────────────────────────────────────────

def _handle_reaction(event: dict, *, removed: bool) -> dict:
    emoji = (event.get("reaction") or "").lower()
    item = event.get("item") or {}
    message_ts = item.get("ts", "")
    user = event.get("user", "")

    if not message_ts:
        return _ack()

    signal_name = SIGNAL_FROM_EMOJI.get(emoji)
    if signal_name is None:
        # Not a tracked emoji — ignore. (Avoid trying to learn from every
        # random reaction; the calibration table in preferences.py is the
        # source of truth for what counts.)
        return _ack()

    meta = meta_for(message_ts)
    if not meta:
        # Not a tracked verdict card — drop silently.
        print(f"  reaction {emoji!r} on untracked ts={message_ts} — ignoring")
        return _ack()

    # `reaction_removed` inverts the effect: we record the ORIGINAL signal
    # name (e.g. "reaction_thumbsup") and set `removed=true`. The aggregator
    # in scripts/preferences.py negates the weight when it sees this flag, so
    # un-reacting a 👍 cancels the original +1.0 instead of adding another.
    final_signal = signal_name
    extra: dict = {}
    if removed:
        extra["removed"] = True

    signal_log.append(
        signal=final_signal,
        tool=meta.get("tool", ""),
        category=meta.get("category", ""),
        tags=meta.get("tags", []),
        user=user,
        message_ts=message_ts,
        extra={**extra, "verdict": meta.get("verdict", ""),
               "soc2": meta.get("soc2", "")},
    )
    return _ack()


# ── Thread replies ───────────────────────────────────────────────────────────

def _handle_thread_reply(event: dict) -> dict:
    """A non-bot user posted a thread reply on one of our verdict cards.

    Engagement signal: even neutral discussion is more valuable than silence.
    """
    parent_ts = event.get("thread_ts", "")
    user = event.get("user", "")
    if not parent_ts:
        return _ack()

    meta = meta_for(parent_ts)
    if not meta:
        return _ack()

    signal_log.append(
        signal="thread_reply",
        tool=meta.get("tool", ""),
        category=meta.get("category", ""),
        tags=meta.get("tags", []),
        user=user,
        message_ts=parent_ts,
        extra={"text_preview": (event.get("text") or "")[:120]},
    )
    return _ack()


# ── Meta lookup (public; reused by button_dispatch.py) ──────────────────────

def meta_for(message_ts: str) -> dict:
    """Resolve a Slack message_ts to its {tool, category, tags, ...} meta.

    Reads from the GitHub-mirrored briefings/*-meta.json files. Latest
    file (by filename) is checked first; falls back through the recent
    history so reactions on older briefings still resolve.
    """
    if not message_ts:
        return {}
    if not radar_query._ensure_mirror():
        return {}

    meta_dir = radar_query.LOCAL_MIRROR / "briefings"
    if not meta_dir.exists():
        return {}

    # Newest first — typical reaction is on this week's briefing.
    meta_files = sorted(meta_dir.glob("*-meta.json"), reverse=True)
    for path in meta_files[:8]:  # cap lookup to recent ~2 months
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        v_map = data.get("verdicts") or {}
        if message_ts in v_map:
            entry = dict(v_map[message_ts])
            entry["briefing"] = path.stem.replace("-meta", "")
            return entry
    return {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ack() -> dict:
    return {"statusCode": 200, "body": ""}
