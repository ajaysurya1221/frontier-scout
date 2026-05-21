#!/usr/bin/env python3
"""
AI Telemetry — Monthly Synthesizer (v3).

Runs on the 1st of each month via Bitbucket Pipelines. Reads the radar + skills
log + last 8 weekly briefings, then uses Opus 4.7 with extended thinking to
identify patterns, momentum, blind spots, and what to focus on next month.

Needs at least 4 weekly briefings to produce useful output.
"""

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import anthropic

from cost_tracker import log_call
from llm_client import STATS as LLM_STATS, call_with_retry
from prompts import cached_system_blocks
import quality_logger
from tools import SYNTHESIS_TOOL
import slack_post

CLIENT: anthropic.Anthropic | None = None
MODEL = "claude-opus-4-7"
REPO_ROOT = Path(__file__).parent.parent
OUTPUT = REPO_ROOT / "MONTHLY_SYNTHESIS.md"
THINKING_BUDGET = 8000


def _client() -> anthropic.Anthropic:
    """Create the Anthropic client only when a live synthesis call is made."""
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for synthesis model calls")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT


def _main_impl():
    radar = (REPO_ROOT / "tech-radar.md").read_text()
    skills_log = (REPO_ROOT / "skills-log.md").read_text()

    briefings_dir = REPO_ROOT / "briefings"
    briefing_files = sorted(briefings_dir.glob("*.md")) if briefings_dir.exists() else []
    if len(briefing_files) < 4:
        # Fall back to legacy archive/signals/ if briefings/ is empty
        briefing_files = sorted((REPO_ROOT / "archive" / "signals").glob("*.md"))
    if len(briefing_files) < 4:
        print(f"Only {len(briefing_files)} weekly briefings — need ≥4. Skipping.")
        return

    recent = briefing_files[-8:]
    recent_text = "\n\n---\n\n".join(p.read_text() for p in recent)
    month = datetime.now().strftime("%Y-%m")

    user_prompt = (
        f"Synthesize this month's intelligence into a structured monthly synthesis.\n\n"
        f"TECH RADAR:\n{radar}\n\n"
        f"SKILLS LOG:\n{skills_log}\n\n"
        f"RECENT BRIEFINGS (last {len(recent)} weeks):\n{recent_text}\n\n"
        f"Reference real entries — no generic platitudes. Month: {month}."
    )

    # Opus 4.7 uses adaptive thinking; tool_choice cannot be forced with thinking on.
    resp = call_with_retry(
        _client(),
        "synth",
        model=MODEL,
        max_tokens=THINKING_BUDGET + 4000,
        thinking={"type": "adaptive"},
        system=cached_system_blocks(),
        tools=[SYNTHESIS_TOOL],
        tool_choice={"type": "auto"},
        messages=[{
            "role": "user",
            "content": user_prompt + "\n\nYou MUST call `emit_synthesis` — do not respond with text only.",
        }],
        extra_body={"output_config": {"effort": "high"}},
    )
    cost = log_call("synth", MODEL, resp.usage)
    print(f"  Opus (adaptive thinking, high effort): "
          f"{resp.usage.input_tokens} in + {resp.usage.output_tokens} out = ${cost:.4f}")

    tool_use = next(
        (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_use is None:
        print("⚠️  Synth: Opus did not emit a tool call — skipping write")
        return
    synthesis = tool_use.input

    md = _render_markdown(month, synthesis)
    existing = OUTPUT.read_text() if OUTPUT.exists() else "# Monthly Syntheses\n\n"
    OUTPUT.write_text(existing + "\n---\n\n" + md + "\n")
    print(f"✅ Synthesis → {OUTPUT}")

    print("📣 Posting to Slack...")
    blocks = slack_post.synth_blocks(month, synthesis)
    slack_post.post(blocks)

    print(f"💰 Synthesis cost: ${cost:.4f} · LLM retries: {LLM_STATS.total_retries}")
    quality_logger.log_run(
        "synth",
        total_cost_usd=round(cost, 6),
        llm_retries_total=LLM_STATS.total_retries,
    )


def main():
    """Top-level entry that always logs a quality row, even on crash."""
    start = time.time()
    try:
        _main_impl()
    except BaseException as exc:  # noqa: BLE001
        print(f"\n💥 Synth CRASHED: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        quality_logger.log_run(
            "synth",
            crashed=True,
            error_type=type(exc).__name__,
            error_msg=str(exc)[:500],
            duration_s=round(time.time() - start, 2),
            llm_retries_total=LLM_STATS.total_retries,
            last_retry_error=LLM_STATS.last_error,
        )
        raise


def _render_markdown(month: str, s: dict) -> str:
    focus = s["focus_this_month"]
    return "\n".join([
        f"## {month} — Monthly Synthesis",
        "",
        "### What you've been exploring",
        s["exploration_summary"],
        "",
        "### Momentum check",
        f"- **Adopted**: {', '.join(s['adopted']) or '_nothing yet_'}",
        f"- **Stalled**: {', '.join(s['stalled']) or '_none_'}",
        f"- **Blind spots**: {', '.join(s['blind_spots']) or '_none_'}",
        "",
        "### One thing to focus on this month",
        f"**{focus['tool']}** — {focus['rationale']}",
        f"🧪 Lab suggestion: {focus['lab_suggestion']}",
        "",
        "### Org opportunity",
        s["org_opportunity"],
    ])


if __name__ == "__main__":
    main()
