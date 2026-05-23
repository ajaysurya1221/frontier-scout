#!/usr/bin/env python3
"""
Frontier Scout — Deep evaluation triggered from Slack.

Invoked by the `evaluate-from-slack` custom GitHub Actions workflow when a teammate
clicks the 📚 Full evaluation button on a verdict card in Slack. The Lambda
backend triggers this pipeline with these variables:

  TOOL        — tool name from the button payload
  URL         — source URL from the verdict
  USER        — Slack username who clicked
  THREAD_TS   — parent message ts (so we reply in the same thread)
  CHANNEL_ID  — Slack channel ID

This script runs a Sonnet evaluation pass over the tool (using EVALUATE_TOOLS
schema from scripts/tools.py if data sources are available), then posts the
result back to the originating Slack thread.

If the heavy GitHub/PyPI/Mem0 lookups aren't useful for a given tool, we
fall back to a structured Sonnet single-call evaluation with the same
verdict rubric Scout uses.
"""

import os
import re
import sys
import time
import traceback
from datetime import datetime

import anthropic

from cost_tracker import log_call
from llm_client import call_with_retry
from prompts import cached_system_blocks
import quality_logger
import slack_post
from tools import VERDICT_TOOL
from validators import validate_verdicts

CLIENT: anthropic.Anthropic | None = None

def _client() -> anthropic.Anthropic:
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for this run")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT
MODEL = "claude-sonnet-4-6"


def _build_evaluation_prompt(tool: str, url: str, user: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        f"Today is {today}. {user} requested a DEEP evaluation of `{tool}` "
        f"via the 📚 Full evaluation button in Slack.\n\n"
        f"Source URL: {url}\n\n"
        f"Produce a single, polished verdict for this tool against the "
        f"standard rubric. Be specific to the configured stack (LangGraph, "
        f"LangChain, FastAPI, AWS, document-heavy AI operations, mid-flight "
        f"SOC2 audit). The verdict will be posted as a Slack reply in the "
        f"thread of the original briefing.\n\n"
        "Keep every field concise and evidence-backed. If the tool name is "
        "ambiguous, explicitly state the ambiguity in `what` and choose the "
        "most conservative tier you can justify.\n\n"
        "Include `why_this_week` only when there is a real timing signal "
        "(release, major adoption spike, or security event)."
    )


def _requester_label(user: str) -> str:
    """Format requester safely whether USER is a Slack ID or a username."""
    if re.fullmatch(r"[UW][A-Z0-9]{8,}", user or ""):
        return f"<@{user}>"
    safe = (user or "unknown").lstrip("@")
    return f"@{safe}"


def _post_reply(verdict: dict, channel: str, thread_ts: str, user: str) -> bool:
    """Post the verdict card as a reply in the originating thread."""
    requester = _requester_label(user)
    intro_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Deep evaluation* · requested by {requester}\n"
                    "Independent second pass on this verdict."
                ),
            },
        },
    ]
    _outer, attachments = slack_post._threaded_verdict_card(
        1,
        verdict,
        include_actions=False,
        show_rank=False,
    )
    fallback = (
        f"Deep evaluation for {verdict.get('tool_name', 'tool')}: "
        f"{verdict.get('verdict', 'assess').upper()} · "
        f"next action {verdict.get('next_action', '')}"
    )
    try:
        slack_post._with_slack_retry(
            slack_post._post_thread_reply,
            thread_ts,
            intro_blocks,
            attachments,
            op_label="slack evaluate-from-slack reply",
            dead_letter_payload={
                "thread_ts": thread_ts,
                "blocks": intro_blocks,
                "attachments": attachments,
            },
            text_fallback=fallback[:220],
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  Reply failed: {e}")
        return False


def _main_impl() -> None:
    start = time.time()
    tool = os.environ.get("TOOL", "").strip()
    url = os.environ.get("URL", "").strip()
    user = os.environ.get("USER", "unknown")
    thread_ts = os.environ.get("THREAD_TS", "").strip()
    channel = os.environ.get("CHANNEL_ID", "") or os.environ.get("SLACK_CHANNEL_ID", "")

    if not tool:
        print("❌ TOOL variable missing")
        sys.exit(1)

    print(f"📚 Evaluating {tool!r} (requested by {user}, url={url})")

    prompt = _build_evaluation_prompt(tool, url, user)
    resp = call_with_retry(
        _client(),
        "evaluate-from-slack",
        model=MODEL,
        max_tokens=2000,
        system=cached_system_blocks(),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "emit_verdicts"},
        messages=[{"role": "user", "content": prompt}],
    )
    cost = log_call("evaluate-from-slack", MODEL, resp.usage)
    print(f"  cost ${cost:.4f}")

    tool_use = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
    if tool_use is None:
        print("  Sonnet returned no structured tool output.")
        quality_logger.log_run(
            "evaluate-from-slack",
            tool=tool,
            user=user,
            total_cost_usd=round(cost, 6),
            duration_s=round(time.time() - start, 2),
            slack_posted=False,
            error_type="missing_tool_use",
        )
        return
    verdicts = tool_use.input.get("verdicts") or []
    if not verdicts:
        print("  Sonnet returned no verdict.")
        quality_logger.log_run(
            "evaluate-from-slack",
            tool=tool,
            user=user,
            total_cost_usd=round(cost, 6),
            duration_s=round(time.time() - start, 2),
            slack_posted=False,
            error_type="no_verdicts",
        )
        return

    # Policy gates — same rules as Scout
    final, dropped = validate_verdicts(verdicts, source_items=[{"title": tool, "url": url}])
    if dropped:
        for d in dropped:
            print(f"  ❌ policy dropped: {d['reason']}")
    if not final:
        print("  All verdicts dropped by policy.")
        quality_logger.log_run(
            "evaluate-from-slack",
            tool=tool,
            user=user,
            total_cost_usd=round(cost, 6),
            duration_s=round(time.time() - start, 2),
            slack_posted=False,
            error_type="policy_dropped",
        )
        return

    verdict = final[0]
    if not thread_ts or not channel:
        print("  No thread_ts/channel — printing to stdout instead of posting")
        print(verdict)
        quality_logger.log_run(
            "evaluate-from-slack",
            tool=tool,
            user=user,
            total_cost_usd=round(cost, 6),
            duration_s=round(time.time() - start, 2),
            slack_posted=False,
            error_type="missing_thread_context",
        )
        return

    # Ensure the Slack post helpers know which channel to use
    if channel:
        os.environ["SLACK_CHANNEL_ID"] = channel

    posted = _post_reply(verdict, channel=channel, thread_ts=thread_ts, user=user)
    if posted:
        print(f"✅ Reply posted to thread {thread_ts}")
    else:
        print(f"⚠️ Reply failed for thread {thread_ts}")

    quality_logger.log_run(
        "evaluate-from-slack",
        tool=tool,
        user=user,
        total_cost_usd=round(cost, 6),
        duration_s=round(time.time() - start, 2),
        slack_posted=posted,
    )


def main() -> None:
    try:
        _main_impl()
    except BaseException as exc:  # noqa: BLE001
        print(f"💥 evaluate-from-slack crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        quality_logger.log_run(
            "evaluate-from-slack",
            crashed=True,
            error_type=type(exc).__name__,
            error_msg=str(exc)[:500],
        )
        raise


if __name__ == "__main__":
    main()
