"""
Button click dispatcher — handles `block_actions` from Slack interactivity.

Each verdict card in the briefing has up to three buttons:
  • 🧪 Run Lab          → triggers `lab-from-slack` (only on open-source URLs);
                          the lab pulls the tool, runs a stack-shaped
                          synthetic test in a hermetic subprocess, and replies
                          in thread (~5–10 min). See scripts/lab_runner.py.
  • 📚 Full evaluation  → triggers GitHub Actions `evaluate-from-slack`
  • 📊 Compare           → opens a modal with prior-vs-current verdict (Mem0 data)

Each button carries a `value` JSON blob with the verdict's metadata so we
don't need to re-derive context from the message.

Heavy work is delegated back to GitHub Actions via workflow_dispatch. The
Lambda stays small and only verifies Slack requests, dispatches jobs, and
returns immediate user feedback.
"""

from __future__ import annotations

import json
import os

import urllib.request
import urllib.error

import signal_log


def handle(body: dict) -> dict:
    """Dispatch a `block_actions` payload to the right handler."""
    actions = body.get("actions") or []
    if not actions:
        return _ack()
    action = actions[0]
    action_id = action.get("action_id", "")

    # Overflow menu fires with `selected_option`, not `value`. Normalize so
    # downstream code sees a consistent shape.
    if action.get("type") == "overflow":
        opt = action.get("selected_option") or {}
        value = opt.get("value", "")
    else:
        value = action.get("value", "")

    try:
        ctx = json.loads(value) if value else {}
    except json.JSONDecodeError:
        ctx = {"raw": value}

    user = body.get("user", {})
    user_id = user.get("id", "")
    user_name = user.get("username", "")
    response_url = body.get("response_url", "")

    # Emit a taste-model signal for every actionable click. Fire-and-forget;
    # signal_log.append() never raises. Tags get enriched from the briefings
    # mirror inside reaction_dispatch._meta_for(), so even though the button
    # `value` doesn't carry tags directly we still record the tool and let
    # the aggregator resolve topics via the meta map.
    message_ts = body.get("message", {}).get("ts", "")
    _emit_button_signal(action_id, ctx, user_name or user_id, message_ts)

    # Overflow menu items route by the embedded `action` key in the value blob
    if action_id == "verdict_overflow":
        return _handle_overflow(ctx, response_url, user_name or user_id)

    if action_id == "verdict_lab":
        return _trigger_workflow(
            "lab-from-slack",
            variables={
                "TOOL": ctx.get("tool_name", "unknown"),
                "URL": ctx.get("source_url", ""),
                "USER": user_name or user_id,
            },
            response_url=response_url,
            confirmation=(
                f":test_tube: Lab running on *{ctx.get('tool_name', 'tool')}* "
                "against your configured stack patterns. "
                "Results in this thread in ~5–15 min — longer for heavier "
                "packages (transformers, torch). "
                "Hermetic subprocess — no app secrets reach the tool."
            ),
        )

    if action_id == "verdict_evaluate":
        return _trigger_workflow(
            "evaluate-from-slack",
            variables={
                "TOOL": ctx.get("tool_name", "unknown"),
                "URL": ctx.get("source_url", ""),
                "USER": user_name or user_id,
                "THREAD_TS": body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts", ""),
                "CHANNEL_ID": body.get("channel", {}).get("id", ""),
            },
            response_url=response_url,
            confirmation=f":books: Running deep evaluation on *{ctx.get('tool_name', 'tool')}*. "
                         f"Results will reply in this thread in ~60s.",
        )

    if action_id == "verdict_compare":
        return _open_compare_modal(body, ctx)

    return _ephemeral_via_response_url(
        response_url,
        f"Unknown action: `{action_id}`",
    )


# ── Taste-model signal emission ──────────────────────────────────────────────

# Map button action_id → canonical signal name. Kept in sync with the
# SIGNAL_WEIGHTS table in scripts/preferences.py.
_BUTTON_SIGNAL: dict[str, str] = {
    "verdict_lab":       "lab_queued",
    "verdict_evaluate":  "evaluate_requested",
    "verdict_compare":   "compare_opened",
}

# Overflow sub-actions: same shape, but the action lives in ctx["a"]
# (compact) or ctx["action"] (legacy fallback).
_OVERFLOW_SIGNAL: dict[str, str] = {
    "snooze_30d":  "snoozed",
    "mark_seen":   "marked_seen",
    # copy_link is read-only — no signal.
}


def _emit_button_signal(action_id: str, ctx: dict, user: str, message_ts: str) -> None:
    """Best-effort write of one signal line for a button or overflow click."""
    if action_id == "verdict_overflow":
        sub = ctx.get("a") or ctx.get("action", "")
        signal = _OVERFLOW_SIGNAL.get(sub)
        tool = ctx.get("t") or ctx.get("tool_name", "")
    else:
        signal = _BUTTON_SIGNAL.get(action_id)
        tool = ctx.get("tool_name", "")
    if not signal or not tool:
        return

    # Look up category + tags from the briefings/<date>-meta.json mirror.
    # The overflow's compact `value` field can't carry tags, so we resolve
    # them by the same Slack message_ts the user just clicked on.
    import reaction_dispatch  # local import; avoids cold-start cost on slash commands
    meta = reaction_dispatch.meta_for(message_ts) if message_ts else {}

    signal_log.append(
        signal=signal,
        tool=tool,
        category=ctx.get("category") or meta.get("category", ""),
        tags=meta.get("tags") or [],
        user=user,
        message_ts=message_ts,
    )


# ── GitHub Actions workflow trigger ──────────────────────────────────────────

def _trigger_workflow(
    selector: str,
    variables: dict[str, str],
    response_url: str,
    confirmation: str,
) -> dict:
    """Dispatch a GitHub Actions workflow by filename."""
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    branch = os.environ.get("GH_BRANCH") or os.environ.get("GITHUB_REF_NAME", "main")
    if not (repo and token):
        return _ephemeral_via_response_url(
            response_url,
            ":warning: GitHub Actions trigger not configured (`GH_REPO` + `GH_TOKEN`).",
        )

    workflow = selector if selector.endswith((".yml", ".yaml")) else f"{selector}.yml"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    payload = {
        "ref": branch,
        "inputs": {k: str(v) for k, v in variables.items()},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "frontier-scout-slack-lambda",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            ok = 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:200]
        return _ephemeral_via_response_url(
            response_url,
            f":x: GitHub Actions dispatch failed ({e.code}): `{body}`",
        )
    except Exception as e:  # noqa: BLE001
        return _ephemeral_via_response_url(
            response_url,
            f":x: GitHub Actions dispatch failed: {e}",
        )

    if not ok:
        return _ephemeral_via_response_url(response_url, ":x: GitHub returned non-2xx.")

    return _ephemeral_via_response_url(response_url, confirmation)


# ── Compare modal (Mem0 prior-verdict surface) ───────────────────────────────

def _handle_overflow(ctx: dict, response_url: str, user: str) -> dict:
    """Route overflow-menu selections (mark seen / snooze / copy link).

    Overflow option `value` fields are capped at 150 chars by Slack, so the
    poster (`scripts/slack_post._overflow_value`) packs only `{a, t}` — the
    action id and the (truncated) tool name. We still read the old
    `{action, tool_name, source_url}` shape so messages already-in-flight
    from before this deploy keep working.
    """
    sub = ctx.get("a") or ctx.get("action", "")
    tool = ctx.get("t") or ctx.get("tool_name", "tool")
    source_url = ctx.get("u") or ctx.get("source_url", "")  # only old payloads carry u

    if sub == "copy_link":
        # New compact payloads no longer carry the URL — resolve it from
        # the latest briefing the Lambda already mirrors locally.
        src = source_url or _resolve_source_url(tool)
        if not src:
            return _ephemeral_via_response_url(
                response_url,
                f":link: Source link for *{tool}* is in the verdict header above "
                f"(click the bold tool name).",
            )
        return _ephemeral_via_response_url(
            response_url,
            f":link: Source for *{tool}*:\n{src}",
        )

    if sub == "mark_seen":
        # Seed Mem0 with a synthetic "already evaluated" note so the next
        # Scout's prior-filter skips this tool. Triggers the same GitHub
        # Actions pattern as the other buttons. URL is nice-to-have for
        # the Mem0 record — fall back to the briefing-mirror resolver.
        url_for_record = source_url or _resolve_source_url(tool)
        return _trigger_workflow(
            "mark-seen-from-slack",
            variables={"TOOL": tool, "URL": url_for_record, "USER": user, "NOTE": "marked-seen-via-slack"},
            response_url=response_url,
            confirmation=f":white_check_mark: *{tool}* marked as already evaluated. "
                         f"Next Scout's prior-filter will skip it.",
        )

    if sub == "snooze_30d":
        return _trigger_workflow(
            "snooze-from-slack",
            variables={"TOOL": tool, "DAYS": "30", "USER": user},
            response_url=response_url,
            confirmation=f":mute: *{tool}* snoozed for 30 days. "
                         f"No new verdicts on it until {_thirty_days_from_now()}.",
        )

    return _ephemeral_via_response_url(response_url, f"Unknown overflow action: `{sub}`")


def _thirty_days_from_now() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")


def _resolve_source_url(tool: str) -> str:
    """Find a tool's source URL in the latest briefing.

    Slack overflow option `value` fields are capped at 150 chars, so we can't
    round-trip the URL through the overflow payload. The Lambda already
    mirrors the repo (briefings included) via `github_mirror`, so we can
    grep for the tool name there and pick the nearest URL.
    """
    if not tool:
        return ""
    try:
        import radar_query
        if not radar_query._ensure_mirror():
            return ""
        briefings = sorted(
            (radar_query.LOCAL_MIRROR / "briefings").glob("*.md"),
            reverse=True,
        )
        if not briefings:
            return ""
        text = briefings[0].read_text(errors="ignore")
        import re
        # Briefing renders each verdict with the tool name followed within
        # a few hundred chars by its source URL. Find a tool-name hit and
        # pick the nearest following URL.
        for m in re.finditer(re.escape(tool[:40]), text, re.I):
            tail = text[m.end(): m.end() + 600]
            mu = re.search(r"https?://\S+", tail)
            if mu:
                return mu.group(0).rstrip(").,;:")
    except Exception as e:  # noqa: BLE001
        print(f"  _resolve_source_url({tool!r}) failed: {e}")
    return ""


def _open_compare_modal(body: dict, ctx: dict) -> dict:
    """Open a Slack modal showing prior-vs-current verdict for the tool."""
    try:
        from slack_sdk import WebClient  # type: ignore
    except ImportError:
        return _ephemeral_via_response_url(
            body.get("response_url", ""),
            ":warning: Modal unavailable (slack_sdk not bundled).",
        )

    tool = ctx.get("tool_name", "tool")
    trigger_id = body.get("trigger_id", "")
    if not trigger_id:
        return _ephemeral_via_response_url(
            body.get("response_url", ""),
            ":warning: No trigger_id on the action — can't open modal.",
        )

    # Look up prior verdict from Mem0 (best-effort)
    import radar_query
    radar_query._ensure_mirror()
    prior = radar_query._mem0_lookup(tool) or {}
    prior_meta = prior.get("metadata") or {}
    prior_doc = (prior.get("document") or "").strip()

    current_verdict = ctx.get("verdict", "?")
    current_soc2 = ctx.get("soc2", "?")

    view = {
        "type": "modal",
        "callback_id": "verdict_compare_view",
        "title": {"type": "plain_text", "text": "Compare verdict"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"📊  {tool}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"*Current*\nverdict: *{current_verdict.upper()}*  ·  SOC2: *{current_soc2}*"
            )}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"*Prior (Mem0)*\nverdict: *{(prior_meta.get('verdict') or '—').upper()}*  ·  "
                f"SOC2: *{prior_meta.get('soc2') or '—'}*  ·  "
                f"added: _{prior_meta.get('added_at', '—')}_"
            )}},
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f"```\n{prior_doc[:1500] or '(no prior Mem0 record found)'}\n```"
            )}},
        ],
    }

    try:
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        client.views_open(trigger_id=trigger_id, view=view)
    except Exception as e:  # noqa: BLE001
        return _ephemeral_via_response_url(
            body.get("response_url", ""),
            f":x: Modal open failed: {e}",
        )
    return _ack()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ack() -> dict:
    """Slack expects a 200 within 3s; an empty body acknowledges."""
    return {"statusCode": 200, "body": ""}


def _ephemeral_via_response_url(response_url: str, text: str) -> dict:
    """For block_actions, the most reliable reply path is to POST the response
    payload to `response_url` (rather than returning JSON body). This lets us
    take time to do work (GitHub Actions dispatch) and still cleanly reply later.
    """
    if not response_url:
        return {"statusCode": 200, "body": ""}
    payload = json.dumps({"response_type": "ephemeral", "text": text}).encode("utf-8")
    req = urllib.request.Request(
        response_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=4).read()
    except Exception as e:  # noqa: BLE001
        print(f"  response_url POST failed: {e}")
    return {"statusCode": 200, "body": ""}
