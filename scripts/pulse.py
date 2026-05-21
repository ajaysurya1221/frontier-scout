#!/usr/bin/env python3
"""
AI Telemetry — Daily Tier-S Pulse (v3).

Polls high-signal sources every day. Posts to Slack ONLY when a new release
scores ≥8 (major drop) AND survives the RLAIF judge. Silent days stay silent.

Deduplication: pulse-log.md tracks every URL we've ever posted.

Env: same as scout.py.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import requests

from cost_tracker import log_call
from prompts import cached_system_blocks
from tools import SCORE_ITEMS_TOOL, VERDICT_TOOL
import judge as judge_mod
import quality_logger
import slack_post
from llm_client import STATS as LLM_STATS, call_with_retry
from validators import validate_verdicts

CLIENT: anthropic.Anthropic | None = None
MODEL = "claude-sonnet-4-6"
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=24)

REPO_ROOT = Path(__file__).parent.parent
PULSE_LOG = REPO_ROOT / "pulse-log.md"           # legacy human-readable log
PULSE_STATE = REPO_ROOT / "pulse-state.json"     # machine-readable state machine
PULSE_ARCHIVE = REPO_ROOT / "archive" / "pulse"

MAX_PULSE_ITEMS = 50
TIER_S_THRESHOLD = 8  # loosened from v1's 9 — v1 was too strict, missed real drops

USER_AGENT = "ai-telemetry/2.0 (+https://github.com/YOUR_ORG/ai-telemetry)"


def _client() -> anthropic.Anthropic:
    """Create the Anthropic client only when a live Pulse call is made."""
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Pulse model calls")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT

# Tier-S sources: frontier model labs + core infrastructure.
TIER_S_GITHUB = [
    ("anthropics/anthropic-cookbook",      "Anthropic"),
    ("anthropics/anthropic-sdk-python",    "Anthropic SDK"),
    ("openai/openai-python",               "OpenAI"),
    ("openai/openai-agents-python",        "OpenAI Agents SDK"),
    ("langchain-ai/langchain",             "LangChain"),
    ("langchain-ai/langgraph",             "LangGraph"),
    ("google-gemini/generative-ai-python", "Google Gemini"),
    ("huggingface/transformers",           "HuggingFace Transformers"),
    ("vllm-project/vllm",                  "vLLM"),
    ("ollama/ollama",                      "Ollama"),
]


def fetch_tier_s_releases() -> list[dict]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    items = []
    for repo, name in TIER_S_GITHUB:
        try:
            url = f"https://api.github.com/repos/{repo}/releases?per_page=5"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            for r in resp.json():
                if r.get("draft") or r.get("prerelease"):
                    continue
                pub = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
                if pub < CUTOFF:
                    continue
                items.append({
                    "source": name,
                    "title": f"{name} {r['tag_name']}",
                    "url": r["html_url"],
                    "summary": (r.get("body") or "")[:500],
                    "when": pub.strftime("%Y-%m-%d %H:%M UTC"),
                    "date": pub.strftime("%Y-%m-%d"),
                })
        except Exception as e:
            print(f"  {repo}: {e}")
    return items


def _load_state() -> dict:
    """Load pulse-state.json (the dedupe state machine).

    Migration: any URL found only in the legacy pulse-log.md is treated as
    `posted` so we don't re-post historical items.
    """
    if PULSE_STATE.exists():
        try:
            return json.loads(PULSE_STATE.read_text())
        except (json.JSONDecodeError, OSError):
            print(f"  ⚠️  pulse-state.json corrupt, starting fresh")
            return {}
    # Migrate legacy log
    state: dict = {}
    if PULSE_LOG.exists():
        for line in PULSE_LOG.read_text().splitlines():
            # Lines look like: "- `2026-05-20` https://..."
            for token in line.split():
                if token.startswith("http"):
                    state[token] = {
                        "state": "posted",
                        "first_seen": "legacy",
                        "last_attempt": "legacy",
                    }
                    break
    return state


def _save_state(state: dict) -> None:
    PULSE_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PULSE_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(PULSE_STATE)


def already_seen(state: dict, url: str) -> bool:
    """True iff the URL is in a terminal state (posted or vetoed).

    `failed_delivery` is NOT terminal — those URLs are retried on the next
    run. This is the Round 3 fix: v2 marked items seen unconditionally,
    which silently dropped any failed-Slack-delivery alerts.
    """
    entry = state.get(url)
    if entry is None:
        return False
    return entry.get("state") in {"posted", "vetoed"}


def record_state(state: dict, url: str, new_state: str) -> None:
    """Record a state transition. new_state in {posted, vetoed, failed_delivery}."""
    now = datetime.now(timezone.utc).isoformat()
    if url not in state:
        state[url] = {"first_seen": now}
    state[url]["state"] = new_state
    state[url]["last_attempt"] = now


def score_for_tier_s(items: list[dict]) -> tuple[list[dict], float]:
    """Score each item; only those scoring ≥TIER_S_THRESHOLD continue."""
    if not items:
        return [], 0.0
    if len(items) > MAX_PULSE_ITEMS:
        items = items[:MAX_PULSE_ITEMS]

    batch = "\n\n".join(
        f"[{i}] {item['source']} | {item['title']}\n{item['summary'][:250]}"
        for i, item in enumerate(items)
    )
    resp = call_with_retry(
        _client(),
        "pulse-score",
        model=MODEL,
        max_tokens=1500,
        system=cached_system_blocks(),
        tools=[SCORE_ITEMS_TOOL],
        tool_choice={"type": "tool", "name": "score_items"},
        messages=[{
            "role": "user",
            "content": (
                f"Score these {len(items)} Tier-S candidates. Reserve 9-10 for major "
                f"releases (new model family, breaking API, paradigm shift). 8 for "
                f"substantial feature releases worth alerting on. 0-5 for patch / "
                f"chore / dependency releases.\n\n{batch}"
            ),
        }],
    )
    cost = log_call("pulse-score", MODEL, resp.usage)
    print(f"  Pulse score: {resp.usage.input_tokens} in + {resp.usage.output_tokens} out "
          f"(cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)}) = ${cost:.4f}")

    tool_use = next(b for b in resp.content if b.type == "tool_use")
    fires: list[dict] = []
    for entry in tool_use.input["scores"]:
        i = entry["index"]
        if 0 <= i < len(items):
            items[i]["score"] = entry["score"]
            items[i]["category"] = entry["category"]
            if entry["score"] >= TIER_S_THRESHOLD:
                fires.append(items[i])
    return fires, cost


def generate_verdict_for(item: dict) -> tuple[dict | None, float]:
    """Generate a single verdict for a Tier-S firing item."""
    today = datetime.now().strftime("%Y-%m-%d")
    body = (
        f"SOURCE: {item['source']}\nTITLE: {item['title']}\nURL: {item['url']}\n"
        f"CATEGORY: {item.get('category', 'tool')}\nDATE: {item['date']}\n"
        f"SUMMARY: {item['summary']}"
    )
    resp = call_with_retry(
        _client(),
        "pulse-verdict",
        model=MODEL,
        max_tokens=1500,
        system=cached_system_blocks(),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "emit_verdicts"},
        messages=[{
            "role": "user",
            "content": (
                f"Today is {today}. Emit a verdict for this Tier-S drop. "
                f"If it doesn't deserve one (patch release, chore), return empty.\n\n{body}"
            ),
        }],
    )
    cost = log_call("pulse-verdict", MODEL, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    verdicts = tool_use.input.get("verdicts") or []
    return (verdicts[0] if verdicts else None), cost


def _main_impl():
    start = time.time()
    print(f"⚡ Pulse v3 — past 24h since {CUTOFF.strftime('%Y-%m-%d %H:%MZ')}\n")
    state = _load_state()

    items = fetch_tier_s_releases()
    items = [i for i in items if not already_seen(state, i["url"])]
    print(f"📥 {len(items)} new Tier-S candidates (not already posted/vetoed)")

    if not items:
        print("Silent day. Nothing to post.")
        quality_logger.log_run("pulse", items_scanned=0)
        return

    fires, score_cost = score_for_tier_s(items)
    total_cost = score_cost

    # Items that didn't fire are marked vetoed (score too low) so they don't
    # re-enter the loop tomorrow with the same low score.
    # DRY_RUN: never mutate dedupe state — this is a preview, not a delivery.
    dry_run = os.environ.get("DRY_RUN") == "1"
    if not dry_run:
        for item in items:
            if item not in fires:
                record_state(state, item["url"], "vetoed")

    if not fires:
        print(f"⚡ No items scored ≥{TIER_S_THRESHOLD}. Silent.")
        if not dry_run:
            _save_state(state)
        quality_logger.log_run(
            "pulse", items_scanned=len(items), verdicts_post_judge=0,
            total_cost_usd=round(total_cost, 6),
        )
        return

    print(f"🔥 {len(fires)} Tier-S drop(s) above threshold")
    posted = 0
    policy_dropped = 0
    for item in fires:
        print(f"\n  → {item['title']} (score={item['score']})")

        verdict, vcost = generate_verdict_for(item)
        total_cost += vcost
        if verdict is None:
            print("    Sonnet declined to verdict — vetoing.")
            if not dry_run:
                record_state(state, item["url"], "vetoed")
            continue

        # RLAIF judge over the single verdict
        judge_result, jcost = judge_mod.critique([verdict], [item])
        total_cost += jcost
        final = judge_mod.apply_judge_decisions([verdict], [item], judge_result)
        if not final:
            print(f"    Judge vetoed: {judge_result.get('judge_summary', '')}")
            if not dry_run:
                record_state(state, item["url"], "vetoed")
            continue

        # Policy gates after the judge
        kept, dropped = validate_verdicts(final, source_items=[item])
        if dropped:
            for d in dropped:
                print(f"    ❌ policy dropped: {d['reason']}")
            policy_dropped += len(dropped)
        if not kept:
            if not dry_run:
                record_state(state, item["url"], "vetoed")
            continue

        v = kept[0]
        blocks = slack_post.pulse_blocks(
            source=item["source"], title=item["title"], url=item["url"],
            when=item["when"], verdict=v,
        )
        # DRY_RUN: print the payload but DO NOT mutate dedupe state — otherwise
        # a dry-run preview marks items posted and they never alert for real.
        if os.environ.get("DRY_RUN") == "1":
            slack_post.post(blocks)  # prints to stdout
            posted += 1
            print("    (DRY_RUN — pulse-state not mutated)")
            continue
        try:
            slack_post.post(blocks)
            record_state(state, item["url"], "posted")
            posted += 1
        except Exception as e:
            # Don't mark as seen — next run will retry.
            print(f"    Slack post failed (will retry next run): {e}")
            record_state(state, item["url"], "failed_delivery")

    if not dry_run:
        _save_state(state)

    today = datetime.now().strftime("%Y-%m-%d")
    PULSE_ARCHIVE.mkdir(parents=True, exist_ok=True)
    log_lines = []
    for item in fires:
        log_lines.append(
            f"## {item['title']} (score {item.get('score', '?')})\n"
            f"{item['url']}\n_{item['when']}_\n\n{item['summary']}\n"
        )
    if log_lines:
        (PULSE_ARCHIVE / f"{today}.md").write_text("\n".join(log_lines))

    duration = round(time.time() - start, 2)
    quality_logger.log_run(
        "pulse",
        items_scanned=len(items),
        verdicts_post_judge=posted,
        policy_dropped=policy_dropped,
        total_cost_usd=round(total_cost, 6),
        duration_s=duration,
        llm_retries_total=LLM_STATS.total_retries,
        llm_retries_by_component=dict(LLM_STATS.by_component),
    )
    print(
        f"\n✅ Posted {posted}/{len(fires)} · cost ${total_cost:.4f} · "
        f"{duration}s · LLM retries: {LLM_STATS.total_retries}"
    )


def main():
    """Top-level entry that always logs a quality row, even on crash."""
    import sys
    start = time.time()
    try:
        _main_impl()
    except BaseException as exc:  # noqa: BLE001
        import traceback
        print(f"\n💥 Pulse CRASHED: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        quality_logger.log_run(
            "pulse",
            crashed=True,
            error_type=type(exc).__name__,
            error_msg=str(exc)[:500],
            duration_s=round(time.time() - start, 2),
            llm_retries_total=LLM_STATS.total_retries,
            last_retry_error=LLM_STATS.last_error,
        )
        raise


if __name__ == "__main__":
    main()
