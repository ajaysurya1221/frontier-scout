"""
RLAIF Judge — Opus 4.7 with extended thinking, applied as a third pass over the
Sonnet-generated verdicts before they ship to Slack.

This is the precision lever. The Sonnet pass is a strong generator but occasionally
over-labels maintenance releases as ADOPT or emits awareness-only items. The judge
is a strict reviewer that vetoes those, adjusts tiers, and surfaces missed items.

Flow:
    verdicts (Sonnet output) + scored_items (Sonnet score pass output)
      → critique()
      → apply_judge_decisions()
      → final_verdicts + severity + readiness + judge_meta
"""

from __future__ import annotations

import os
from typing import Any

import anthropic

from cost_tracker import log_call
from llm_client import call_with_retry
from prompts import cached_judge_blocks
from tools import JUDGE_TOOL

CLIENT: anthropic.Anthropic | None = None
JUDGE_MODEL = "claude-opus-4-7"
THINKING_BUDGET = 4000  # tokens


def _client() -> anthropic.Anthropic:
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the judge pass")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT


def critique(
    verdicts: list[dict],
    scored_items: list[dict],
) -> tuple[dict[str, Any], float]:
    """
    Run the Opus judge pass over the draft verdicts.

    Returns: (judge_result, cost_usd) where judge_result has keys:
        decisions: list of {index, action, reason, [new_tier], [severity], [readiness]}
        missed: list of {item_index, suggested_tier, rationale}
        quality_self_rating: "high" | "medium" | "low"
        judge_summary: str
    """
    if not verdicts and not scored_items:
        return _empty_result(), 0.0

    # Render the draft verdicts for the judge to critique
    draft_lines = []
    for i, v in enumerate(verdicts):
        draft_lines.append(
            f"[draft {i}] {v.get('tool_name')} — verdict={v.get('verdict')} "
            f"category={v.get('category')} soc2={v.get('soc2')}\n"
            f"  what: {v.get('what')}\n"
            f"  why_it_matters: {v.get('why_it_matters')}\n"
            f"  adoption_cost: {v.get('adoption_cost')}\n"
            f"  next_action: {v.get('next_action')}\n"
            f"  source_url: {v.get('source_url')}"
        )
    drafts_block = "\n\n".join(draft_lines) if draft_lines else "(no drafts)"

    # Render the top of the scored item pool so the judge can promote misses
    # Limit to top 30 by score to keep the prompt cheap
    top_pool = sorted(
        [it for it in scored_items if it.get("score", 0) >= 5],
        key=lambda x: -x.get("score", 0),
    )[:30]
    pool_lines = []
    for j, it in enumerate(top_pool):
        pool_lines.append(
            f"[item {j}] score={it.get('score')} cat={it.get('category')} "
            f"src={it.get('source')}\n"
            f"  title: {it.get('title', '')[:200]}\n"
            f"  summary: {it.get('summary', '')[:300]}"
        )
    pool_block = "\n\n".join(pool_lines) if pool_lines else "(no scored items above 5)"

    user_message = (
        "Below are the DRAFT VERDICTS produced by the Sonnet verdict pass, followed "
        "by the SCORED ITEM POOL (top 30 by score) the verdict-gen picked from. "
        "Apply the JUDGE RUBRIC in the system prompt. Be strict.\n\n"
        f"━━━ DRAFT VERDICTS ({len(verdicts)}) ━━━\n{drafts_block}\n\n"
        f"━━━ SCORED ITEM POOL (top {len(top_pool)} by score) ━━━\n{pool_block}\n\n"
        "Think through each draft carefully, then call `critique_verdicts` with your "
        "decisions. You MUST call the tool — do not respond with text only."
    )

    # Two-attempt strategy:
    #   1. Adaptive thinking + tool_choice=auto  — preserves chain-of-thought
    #      reasoning but Anthropic forbids forced tool_choice with thinking on.
    #      Live runs occasionally have Opus think extensively then NOT emit a
    #      tool call — that fails our pipeline (fail-closed).
    #   2. If attempt 1 yields no tool_use, retry WITHOUT thinking and with
    #      forced tool_choice. Live probe confirms this reliably emits the
    #      structured judge payload.
    cost = 0.0
    tool_use = None
    used_fallback = False

    resp = call_with_retry(
        _client(),
        "scout-judge",
        model=JUDGE_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=cached_judge_blocks(),
        tools=[JUDGE_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": user_message}],
        extra_body={"output_config": {"effort": "high"}},
    )
    cost += log_call("scout-judge", JUDGE_MODEL, resp.usage)
    cache_read = getattr(resp.usage, "cache_read_input_tokens", 0) or 0
    print(
        f"  Judge pass 1 (thinking): {resp.usage.input_tokens} in + "
        f"{resp.usage.output_tokens} out (cache_read={cache_read}) = ${cost:.4f}"
    )
    tool_use = next(
        (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
        None,
    )

    if tool_use is None:
        # Fallback: no thinking, force the tool call. Cheaper + reliable.
        print("  ⚠️  Judge attempt 1 emitted no tool call — retrying without thinking, forced tool_choice")
        used_fallback = True
        resp2 = call_with_retry(
            _client(),
            "scout-judge-forced",
            model=JUDGE_MODEL,
            max_tokens=4000,
            system=cached_judge_blocks(),
            tools=[JUDGE_TOOL],
            tool_choice={"type": "tool", "name": "critique_verdicts"},
            messages=[{"role": "user", "content": user_message}],
        )
        fallback_cost = log_call("scout-judge-forced", JUDGE_MODEL, resp2.usage)
        cost += fallback_cost
        print(
            f"  Judge pass 2 (forced): {resp2.usage.input_tokens} in + "
            f"{resp2.usage.output_tokens} out = ${fallback_cost:.4f}"
        )
        tool_use = next(
            (b for b in resp2.content if getattr(b, "type", None) == "tool_use"),
            None,
        )

    if tool_use is None:
        # Both attempts failed. NOW fail-closed for real.
        print("  ❌ Both judge attempts emitted no tool call — FAIL-CLOSED")
        return _fail_closed_result(verdicts), cost

    result = dict(tool_use.input)
    if used_fallback:
        result["_judge_used_fallback"] = True
    # Defensive defaults
    result.setdefault("decisions", [])
    result.setdefault("missed", [])
    result.setdefault("quality_self_rating", "medium")
    result.setdefault("judge_summary", "")
    return result, cost


def apply_judge_decisions(
    draft_verdicts: list[dict],
    scored_items: list[dict],
    judge_result: dict,
) -> list[dict]:
    """
    Apply the judge's decisions to produce the final verdict list.

    Returns the final verdicts (in the order: kept/retiered drafts in their original
    order, then promoted misses appended). Each verdict gets `severity` and `readiness`
    fields set from the judge output.
    """
    decisions_by_index = {d["index"]: d for d in judge_result.get("decisions", [])}
    final: list[dict] = []

    for i, v in enumerate(draft_verdicts):
        d = decisions_by_index.get(i)
        if d is None:
            # Judge omitted this draft → treat as veto with no reason
            continue
        action = d.get("action")
        if action == "veto":
            continue
        out = dict(v)
        if action == "retier" and d.get("new_tier"):
            out["verdict"] = d["new_tier"]
        out["severity"] = d.get("severity", "standard")
        out["readiness"] = int(d.get("readiness", 3))
        out["_judge_reason"] = d.get("reason", "")
        final.append(out)

    # Promote any misses the judge surfaced. The judge produces complete verdict
    # blocks (tool_name, what, why_it_matters, adoption_cost, next_action, etc.)
    # so we can render them just like generator-produced verdicts.
    for m in judge_result.get("missed", []):
        idx = m.get("item_index")
        if idx is None or not (0 <= idx < len(scored_items)):
            continue
        item = scored_items[idx]
        final.append({
            "tool_name": m.get("tool_name") or (item.get("title") or "")[:80],
            "verdict": m.get("suggested_tier", "assess"),
            "category": m.get("category") or item.get("category", "tool"),
            "soc2": m.get("soc2", "conditional"),
            "what": m.get("what") or (item.get("summary") or "")[:200],
            "why_it_matters": m.get("why_it_matters", ""),
            "adoption_cost": m.get("adoption_cost", "Not estimated"),
            "next_action": m.get("next_action") or f"evaluate <{m.get('tool_name', 'tool')}>",
            "source_url": item.get("url", ""),
            "severity": m.get("severity", "high"),
            "readiness": int(m.get("readiness", 3)),
            # Carry topic tags from the source item so the channel taste
            # model (preferences.py) can attribute reactions to topics.
            "tags": list(item.get("tags") or []),
            "_judge_reason": "promoted from missed pool",
            "_promoted_by_judge": True,
        })

    return final


def _empty_result() -> dict:
    return {
        "decisions": [],
        "missed": [],
        "quality_self_rating": "high",
        "judge_summary": "No verdicts to judge.",
    }


def _fail_closed_result(verdicts: list[dict]) -> dict:
    """Fallback when judge didn't emit a tool call — VETO every draft.

    This is the SOC2-adjacent safe default: if we can't get a structured
    critique from the judge, we don't ship unjudged verdicts. The operator
    sees a low-rated run in quality-log.jsonl, can inspect, and either
    re-run or accept the empty briefing.
    """
    return {
        "decisions": [
            {
                "index": i,
                "action": "veto",
                "reason": "judge failed to emit structured critique — fail-closed",
            }
            for i in range(len(verdicts))
        ],
        "missed": [],
        "quality_self_rating": "low",
        "judge_summary": (
            "JUDGE FAILED — Opus did not emit a structured tool call. All drafts "
            "vetoed (fail-closed). Operator: inspect the run, re-trigger if a "
            "provider hiccup is suspected."
        ),
        "_judge_failed": True,
    }
