"""
AI Telemetry — Slack interactivity backend.

Single AWS Lambda exposed at a Function URL. Slack calls it whenever a user
interacts with the bot:

  • slash commands       /radar <tool>   /recall <topic>
  • button clicks        🧪 Queue lab · 📚 Full eval · 📊 Compare
  • App Home (future)    persistent dashboard view

The Lambda is stateless beyond reading a read-only S3 mirror of the
ai-telemetry repo (Mem0 store + briefings + tech-radar). Heavy work (running
a lab, running an evaluation) is delegated back to Bitbucket Pipelines via
the existing REST trigger pattern.

Env vars (set in Lambda configuration):
  SLACK_SIGNING_SECRET   — required, used to verify every Slack request
  SLACK_BOT_TOKEN        — required, for replying to slash commands + opening modals
  BB_TOKEN               — required, for triggering Bitbucket pipelines
  BB_WORKSPACE           — Bitbucket workspace slug (e.g. "your-workspace")
  BB_REPO                — Bitbucket repo slug   (e.g. "ai-telemetry")
  S3_MIRROR_BUCKET       — S3 bucket holding the mirrored repo artifacts
  S3_MIRROR_PREFIX       — optional prefix inside the bucket (default "")

Slack request flow:
  Slack → POST Lambda Function URL
        → handler.lambda_handler()
        → slack_verify.verify(headers, body)
        → dispatcher: slash command? button action? view submission?
        → return JSON response (Slack renders inline)
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from slack_verify import verify_slack_request
import bootstrap
import button_dispatch
import radar_query

# Lambda runtime hands us the raw event dict; we shape responses for Slack.


def lambda_handler(event: dict, context: Any) -> dict:
    """AWS Lambda entry point.

    Routes two kinds of invocations:
      1. HTTP via Function URL  → event has `requestContext.http`, body, headers
      2. Direct AWS invocation  → flat payload dict (e.g. `{"action": "bootstrap"}`)
         Authentication is handled by AWS IAM; only callers with
         `lambda:InvokeFunction` can reach this path.
    """
    # Direct AWS invocation path (no HTTP wrapper) — privileged internal actions
    if "requestContext" not in event and event.get("action"):
        return bootstrap.handle(event)

    try:
        return _route(event)
    except Exception as exc:  # noqa: BLE001 — last-resort catch so we always return JSON
        import traceback
        print(f"💥 Lambda crashed: {type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return _ephemeral("Sorry — something went wrong. Operator has been pinged in logs.")


def _route(event: dict) -> dict:
    headers = _normalize_headers(event.get("headers", {}))
    raw_body = _raw_body(event)

    # 1. Verify every request before doing anything else.
    if not verify_slack_request(
        signing_secret=os.environ["SLACK_SIGNING_SECRET"],
        headers=headers,
        body=raw_body,
    ):
        print("❌ Slack signature verification failed")
        return {"statusCode": 401, "body": "invalid signature"}

    # 2. Parse the payload. Slack uses two encodings:
    #    - slash commands + simple events → application/x-www-form-urlencoded
    #    - interactivity (buttons, modals)  → application/x-www-form-urlencoded
    #      with a single `payload=<json>` field
    content_type = headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = json.loads(raw_body)
    else:
        body = _parse_form(raw_body)
        if "payload" in body and isinstance(body["payload"], str):
            body = json.loads(body["payload"])

    # 3. Dispatch
    if body.get("type") == "url_verification":
        # One-time challenge handshake when configuring the endpoint
        return _json({"challenge": body.get("challenge", "")})

    if body.get("type") in {"block_actions", "view_submission"}:
        return button_dispatch.handle(body)

    if body.get("command", "").startswith("/"):
        return _handle_slash_command(body)

    # Unknown event — ack so Slack doesn't retry forever
    print(f"⚠️  Unknown event type: {body.get('type')!r} command={body.get('command')!r}")
    return {"statusCode": 200, "body": ""}


def _handle_slash_command(body: dict) -> dict:
    command = body.get("command", "").lstrip("/")
    text = (body.get("text") or "").strip()
    user_id = body.get("user_id", "")

    if command == "radar":
        return radar_query.radar(text, user_id)
    if command == "recall":
        return radar_query.recall(text, user_id)

    return _ephemeral(f"Unknown command: /{command}")


# ── Slack response helpers ───────────────────────────────────────────────────

def _ephemeral(text: str) -> dict:
    """Reply only the invoking user can see."""
    return _json({"response_type": "ephemeral", "text": text})


def _in_channel(blocks: list[dict] | None = None, text: str = "") -> dict:
    """Reply visible to everyone in the channel."""
    payload: dict = {"response_type": "in_channel"}
    if blocks:
        payload["blocks"] = blocks
    if text:
        payload["text"] = text
    return _json(payload)


def _json(payload: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


# ── Lambda event-shape helpers ───────────────────────────────────────────────

def _normalize_headers(headers: dict) -> dict:
    """Lambda Function URL passes headers preserving case; normalize to lowercase."""
    return {k.lower(): v for k, v in headers.items()}


def _raw_body(event: dict) -> str:
    """Lambda Function URL may base64-encode the body. Return decoded str."""
    body = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return body


def _parse_form(body: str) -> dict:
    """application/x-www-form-urlencoded → dict."""
    from urllib.parse import parse_qs
    parsed = parse_qs(body, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
