"""
Button click dispatcher — handles `block_actions` from Slack interactivity.

Each verdict card in the briefing has three buttons:
  • 🧪 Queue lab        → triggers Bitbucket `lab-from-slack` custom pipeline
  • 📚 Full evaluation  → triggers Bitbucket `evaluate-from-slack` custom pipeline
  • 📊 Compare           → opens a modal with prior-vs-current verdict (Mem0 data)

Each button carries a `value` JSON blob with the verdict's metadata so we
don't need to re-derive context from the message.

Heavy work is delegated back to Bitbucket — same proven pattern the existing
🧪 Slack Workflow Builder trigger uses today, just driven from Lambda
instead of Workflow Builder.
"""

from __future__ import annotations

import json
import os

import urllib.request
import urllib.error
from base64 import b64encode


def handle(body: dict) -> dict:
    """Dispatch a `block_actions` payload to the right handler."""
    actions = body.get("actions") or []
    if not actions:
        return _ack()
    action = actions[0]
    action_id = action.get("action_id", "")
    value = action.get("value", "")
    try:
        ctx = json.loads(value) if value else {}
    except json.JSONDecodeError:
        ctx = {"raw": value}

    user = body.get("user", {})
    user_id = user.get("id", "")
    user_name = user.get("username", "")
    response_url = body.get("response_url", "")

    if action_id == "verdict_lab":
        return _trigger_pipeline(
            "lab-from-slack",
            variables={
                "TOOL": ctx.get("tool_name", "unknown"),
                "URL": ctx.get("source_url", ""),
                "USER": user_name or user_id,
            },
            response_url=response_url,
            confirmation=f":test_tube: Lab queued for *{ctx.get('tool_name', 'tool')}*. "
                         f"You'll see it in `.scratch/labs/` shortly.",
        )

    if action_id == "verdict_evaluate":
        return _trigger_pipeline(
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


# ── Bitbucket pipeline trigger ───────────────────────────────────────────────

def _trigger_pipeline(
    selector: str,
    variables: dict[str, str],
    response_url: str,
    confirmation: str,
) -> dict:
    """POST to Bitbucket's /pipelines/ REST endpoint to trigger a custom pipeline."""
    workspace = os.environ.get("BB_WORKSPACE", "")
    repo = os.environ.get("BB_REPO", "")
    token = os.environ.get("BB_TOKEN", "")
    if not (workspace and repo and token):
        return _ephemeral_via_response_url(
            response_url,
            ":warning: Bitbucket trigger not configured (`BB_WORKSPACE` / `BB_REPO` / `BB_TOKEN`).",
        )

    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pipelines/"
    payload = {
        "target": {
            "ref_type": "branch",
            "type": "pipeline_ref_target",
            "ref_name": "main",
            "selector": {"type": "custom", "pattern": selector},
        },
        "variables": [{"key": k, "value": v} for k, v in variables.items()],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Basic " + b64encode(f"x-token-auth:{token}".encode()).decode(),
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
            f":x: Bitbucket trigger failed ({e.code}): `{body}`",
        )
    except Exception as e:  # noqa: BLE001
        return _ephemeral_via_response_url(
            response_url,
            f":x: Bitbucket trigger failed: {e}",
        )

    if not ok:
        return _ephemeral_via_response_url(response_url, ":x: Bitbucket returned non-2xx.")

    return _ephemeral_via_response_url(response_url, confirmation)


# ── Compare modal (Mem0 prior-verdict surface) ───────────────────────────────

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
    take time to do work (Bitbucket trigger) and still cleanly reply later.
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
