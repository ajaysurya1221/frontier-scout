#!/usr/bin/env python3
"""
AI Telemetry — Deep evaluation triggered from Slack.

Invoked by the `evaluate-from-slack` custom Bitbucket pipeline when a teammate
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
MODEL = "claude-sonnet-4-6"


def _client() -> anthropic.Anthropic:
    """Create the Anthropic client only when a live evaluation is made."""
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for evaluation model calls")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT


def _build_evaluation_prompt(tool: str, url: str, user: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        f"Today is {today}. {user} requested a DEEP evaluation of `{tool}` "
        f"via the 📚 Full evaluation button in Slack.\n\n"
        f"Source URL: {url}\n\n"
        f"Produce a single, polished verdict for this tool against the "
        f"standard rubric. Be specific to the configured stack (LangGraph, "
        f"LangChain, FastAPI, AWS, regulated document intelligence, "
        f"SOC2-style controls). The verdict will be posted as a Slack reply in the "
        f"thread of the original briefing.\n\n"
        f"If the tool name is ambiguous, pick the most likely Python/AI "
        f"interpretation. Include 'Why this week' if there's a recent "
        f"release or trending signal — otherwise omit."
    )


def _post_reply(verdict: dict, channel: str, thread_ts: str, user: str) -> None:
    """Post the verdict card as a reply in the originating thread."""
    sev = verdict.get("severity", "high")
    readiness = int(verdict.get("readiness", 3))
    meter = "▰" * readiness + "▱" * (5 - readiness)
    sev_icon = slack_post.SEVERITY_ICON.get(sev, "⭐")

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                f"📚  *Deep evaluation*  ·  requested by <@{user}>"
            )},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                f"{sev_icon}  "
                f"{slack_post._safe_link(verdict['source_url'], verdict['tool_name'])}  "
                f"·  {slack_post.CATEGORY_EMOJI[verdict['category']]}  "
                f"·  {slack_post.SOC2_BADGE[verdict['soc2']]}"
            )},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"_{verdict['what']}_"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"💡  *Why it matters*\n{verdict['why_it_matters']}"
        )}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"⏱  *Adoption*\n{verdict['adoption_cost']}"},
                {"type": "mrkdwn", "text": f"▶  *Next action*\n{verdict['next_action']}"},
            ],
        },
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"📊  Readiness  `{meter}`  *{readiness}/5*"},
        ]},
    ]
    attachment = {
        "color": slack_post.TIER_COLOR.get(verdict["verdict"], "#9aa0a6"),
        "blocks": blocks,
        "fallback": f"Deep eval: {verdict['tool_name']}",
    }
    try:
        slack_post._with_slack_retry(
            slack_post._post_thread_reply,
            thread_ts,
            None,
            [attachment],
            op_label="slack evaluate-from-slack reply",
            dead_letter_payload={"thread_ts": thread_ts, "attachments": [attachment]},
        )
    except Exception as e:  # noqa: BLE001
        print(f"  Reply failed: {e}")


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

    tool_use = next(b for b in resp.content if b.type == "tool_use")
    verdicts = tool_use.input.get("verdicts") or []
    if not verdicts:
        print("  Sonnet returned no verdict.")
        return

    # Policy gates — same rules as Scout
    final, dropped = validate_verdicts(verdicts, source_items=[{"title": tool, "url": url}])
    if dropped:
        for d in dropped:
            print(f"  ❌ policy dropped: {d['reason']}")
    if not final:
        print("  All verdicts dropped by policy.")
        return

    verdict = final[0]
    if not thread_ts or not channel:
        print("  No thread_ts/channel — printing to stdout instead of posting")
        print(verdict)
        return

    # Ensure the Slack post helpers know which channel to use
    if channel:
        os.environ["SLACK_CHANNEL_ID"] = channel

    _post_reply(verdict, channel=channel, thread_ts=thread_ts, user=user)
    print(f"✅ Reply posted to thread {thread_ts}")

    quality_logger.log_run(
        "evaluate-from-slack",
        tool=tool,
        user=user,
        total_cost_usd=round(cost, 6),
        duration_s=round(time.time() - start, 2),
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
