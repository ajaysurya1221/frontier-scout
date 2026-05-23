#!/usr/bin/env python3
"""Frontier Scout — demo fixtures + offline preview.

``SAMPLE_VERDICTS`` is the canonical fixture set used by:
  * ``scout.run_scan(dry_run=True)`` — returns these directly
  * ``frontier-scout demo`` (CLI) — renders an HTML snapshot
  * Future tests that need realistic verdict shapes without LLM calls

Every verdict here uses the v0.1 schema (category in {skill, mcp_server,
agent_framework, dev_tool, model_drop}; risk + optional fit; readiness 0–5).

Run:
    python scripts/demo.py
    open demo/briefing.html
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REPO_ROOT = Path(__file__).parent.parent
DEMO_DIR = REPO_ROOT / "demo"
SAMPLE_DATE = "2026-05-21"


# ── Sample verdicts (real tools, hand-crafted commentary) ───────────────────

SAMPLE_VERDICTS: list[dict] = [
    {
        "tool_name": "anthropics/skills",
        "verdict": "adopt",
        "category": "skill",
        "risk": "low",
        "fit": "high",
        "what": "Anthropic's official repo of reusable Claude Code Skill bundles — prompt + tool packages installed under ~/.claude/skills/.",
        "why_this_week": "New batch landed: research, security-review, simplify — broadens the catalogue beyond the original three.",
        "why_it_matters": "You run Claude Code daily. Reusable skill bundles cut review setup from a custom prompt every time to one Skill invocation. The code-review and brainstorming skills in particular replace the slash-command shimmying most users do today.",
        "adoption_cost": "~10 min to clone and symlink one skill; zero install cost. Low risk — pure markdown + Python.",
        "next_action": "lab anthropics/skills — verify bundle layout loads under your Claude Code version, then symlink brainstorming.",
        "source_url": "https://github.com/anthropics/skills",
        "severity": "critical",
        "readiness": 5,
        "tags": ["skill", "claude-code", "agentic-coding"],
    },
    {
        "tool_name": "modelcontextprotocol/postgres-mcp",
        "verdict": "trial",
        "category": "mcp_server",
        "risk": "medium",
        "fit": "high",
        "what": "MCP server that exposes a Postgres database to Claude Code as a queryable tool, with read-only and read-write modes.",
        "why_it_matters": "Your stack profile lists Postgres + Next.js. This lets the agent answer 'what's the latest row in users?' directly, without copy-pasting schema into the prompt every time.",
        "adoption_cost": "~30 min to lab-test against a throwaway DB; ~2 hrs to add to a real project with read-only credentials. Medium risk — third-party MCP, audit before connecting to prod.",
        "next_action": "lab modelcontextprotocol/postgres-mcp against a local DB; if the schema introspection looks clean, promote to your MCP config.",
        "source_url": "https://github.com/modelcontextprotocol/servers",
        "severity": "high",
        "readiness": 4,
        "tags": ["mcp", "postgres", "developer-tools"],
    },
    {
        "tool_name": "browser-use/browser-use",
        "verdict": "trial",
        "category": "agent_framework",
        "risk": "medium",
        "fit": "medium",
        "what": "Python agent framework that drives Playwright via an LLM — the agent navigates real websites, fills forms, and clicks buttons.",
        "why_this_week": "v0.4 released structured-output mode that returns typed results instead of raw transcripts.",
        "why_it_matters": "Your stack has FastAPI + Anthropic SDK already; browser-use plugs in as a tool call. For research / scraping flows that today need a custom Playwright script, this collapses to a few lines.",
        "adoption_cost": "~45 min to lab-test on a public site; ~half day to integrate into a real flow with retries. Medium risk — Playwright is heavy, ~150 MB install.",
        "next_action": "lab browser-use/browser-use against a public search page; measure cost-per-task vs the manual Playwright script.",
        "source_url": "https://github.com/browser-use/browser-use",
        "severity": "high",
        "readiness": 4,
        "tags": ["agent-framework", "playwright", "automation"],
    },
    {
        "tool_name": "Qwen/Qwen3-Coder-30B",
        "verdict": "assess",
        "category": "model_drop",
        "risk": "medium",
        "fit": "low",
        "what": "Alibaba's 30B-parameter open-weight coding model on HuggingFace, claiming Claude Sonnet 3.6 parity on HumanEval.",
        "why_this_week": "Public release with ~12 GB quantised weight, fits a single 24 GB GPU.",
        "why_it_matters": "You ship with hosted Claude; running local inference at this scale doesn't pay back for a solo project unless you've got the GPU sitting idle. Worth knowing for the day you do.",
        "adoption_cost": "~2 hrs to set up Ollama + pull weights; ongoing GPU cost if used in flow.",
        "next_action": "Monitor 3 months — revisit if a 7B distill lands with similar HumanEval numbers.",
        "source_url": "https://huggingface.co/Qwen/Qwen3-Coder-30B",
        "severity": "standard",
        "readiness": 3,
        "tags": ["model-drop", "code-llm", "local-inference"],
    },
    {
        "tool_name": "deepseek-ai/DeepSeek-V4-Pro",
        "verdict": "hold",
        "category": "model_drop",
        "risk": "high",
        "fit": "low",
        "what": "67 GB open-weight reasoning model — biggest open release of the quarter.",
        "why_it_matters": "Way over the lab's 5 GB size cap; would need a dedicated multi-GPU box to even download. For a solo developer running on a laptop or single hosted box, this is academic only.",
        "adoption_cost": "Weekend to provision GPU infra + ongoing compute cost. High risk — opaque license clauses on derivative works.",
        "next_action": "Monitor 6 months — revisit if a quantised variant lands under 10 GB.",
        "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
        "severity": "standard",
        "readiness": 4,
        "tags": ["model-drop", "reasoning", "large-model"],
    },
]


SAMPLE_FUNNEL = {
    "items_scanned": 377,
    "dedup_drops": 22,
    "seen_drops": 5,
    "candidates": 350,
    "scored_above_threshold": 19,
    "verdicts_pre_judge": 8,
    "verdicts_post_judge": len(SAMPLE_VERDICTS),
    "judge_self_rating": "high",
    "judge_summary": "Tight upstream pass — vetoed two patch-release noise items, promoted one stack-direct trending repo. Risk calls are conservative.",
    "total_cost_usd": 0.31,
    "duration_s": 232.4,
}


VERDICT_LABEL = {
    "adopt":  "ADOPT",
    "trial":  "TRIAL",
    "assess": "ASSESS",
    "hold":   "HOLD",
}

CATEGORY_LABEL = {
    "skill":           "Skill",
    "mcp_server":      "MCP Server",
    "agent_framework": "Agent Framework",
    "dev_tool":        "Dev Tool",
    "model_drop":      "Model Drop",
}

RISK_LABEL = {"low": "low-risk", "medium": "medium-risk", "high": "high-risk"}


# ── Minimal HTML preview ────────────────────────────────────────────────────


def _render_html() -> str:
    rows = []
    for v in SAMPLE_VERDICTS:
        fit = (v.get("fit") or "—").upper()
        readiness = int(v.get("readiness", 3))
        meter = "▰" * readiness + "▱" * (5 - readiness)
        why_now = v.get("why_this_week", "") or ""
        rows.append(
            f"""
        <article class="verdict tier-{v['verdict']}">
          <header>
            <span class="tier">{VERDICT_LABEL[v['verdict']]}</span>
            <span class="meta">{CATEGORY_LABEL[v['category']]} · {RISK_LABEL[v['risk']]} · fit {fit}</span>
          </header>
          <h2><a href="{v['source_url']}" rel="noopener">{v['tool_name']}</a></h2>
          <p class="what">{v['what']}</p>
          {f'<p class="why-now"><strong>Why this week.</strong> {why_now}</p>' if why_now else ''}
          <p><strong>Why it matters.</strong> {v['why_it_matters']}</p>
          <dl>
            <dt>Adoption cost</dt><dd>{v['adoption_cost']}</dd>
            <dt>Next action</dt><dd><code>{v['next_action']}</code></dd>
            <dt>Readiness</dt><dd><code>{meter}</code> {readiness}/5</dd>
          </dl>
        </article>"""
        )

    body = "\n".join(rows)
    funnel = (
        f"{SAMPLE_FUNNEL['items_scanned']} scanned · "
        f"{SAMPLE_FUNNEL['candidates']} considered · "
        f"{SAMPLE_FUNNEL['verdicts_post_judge']} shipped · "
        f"${SAMPLE_FUNNEL['total_cost_usd']:.2f} · "
        f"judge {SAMPLE_FUNNEL['judge_self_rating']}"
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Frontier Scout — Demo Briefing · {SAMPLE_DATE}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
          max-width: 760px; margin: 2rem auto; padding: 0 1.2rem; color: #1f2937;
          line-height: 1.55; }}
  header.page {{ border-bottom: 1px solid #e5e7eb; padding-bottom: 1rem; margin-bottom: 2rem; }}
  header.page h1 {{ margin: 0 0 .4rem; font-size: 1.5rem; }}
  header.page .funnel {{ color: #6b7280; font-size: .92rem; font-family: ui-monospace, monospace; }}
  article.verdict {{ border-left: 4px solid #9aa0a6; padding: .6rem 0 .6rem 1rem;
                     margin: 1.4rem 0; }}
  article.tier-adopt {{ border-left-color: #16a34a; }}
  article.tier-trial {{ border-left-color: #ca8a04; }}
  article.tier-assess {{ border-left-color: #6b7280; }}
  article.tier-hold {{ border-left-color: #dc2626; }}
  article.verdict header {{ display: flex; gap: .8rem; align-items: baseline; font-size: .85rem; }}
  article.verdict header .tier {{ font-weight: 600; letter-spacing: .04em; }}
  article.verdict header .meta {{ color: #6b7280; }}
  article.verdict h2 {{ margin: .35rem 0 .6rem; font-size: 1.15rem; }}
  article.verdict h2 a {{ color: #1d4ed8; text-decoration: none; }}
  article.verdict p {{ margin: .35rem 0; }}
  article.verdict p.what {{ font-style: italic; color: #374151; }}
  article.verdict dl {{ margin: .6rem 0 0; }}
  article.verdict dt {{ font-weight: 600; color: #374151; margin-top: .3rem; }}
  article.verdict dd {{ margin: 0 0 .2rem; color: #4b5563; }}
  code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: .9em; }}
  footer {{ margin-top: 3rem; color: #9ca3af; font-size: .82rem; text-align: center; }}
</style>
</head><body>
<header class="page">
  <h1>Frontier Scout — Weekly Briefing · {SAMPLE_DATE}</h1>
  <div class="funnel">{funnel}</div>
  <p style="margin: .8rem 0 0;"><strong>Judge's read.</strong> {SAMPLE_FUNNEL['judge_summary']}</p>
</header>
<main>
{body}
</main>
<footer>
  Generated locally by <code>python scripts/demo.py</code>. No network calls, no API keys.
</footer>
</body></html>
"""


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> int:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    html_path = DEMO_DIR / "briefing.html"
    json_path = DEMO_DIR / "verdicts.json"
    log_path = DEMO_DIR / "quality-log.jsonl"

    html_path.write_text(_render_html())
    json_path.write_text(
        json.dumps({"date": SAMPLE_DATE, "verdicts": SAMPLE_VERDICTS}, indent=2)
    )

    sample_log = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": "scout",
        "items_scanned": SAMPLE_FUNNEL["items_scanned"],
        "dedup_drops": SAMPLE_FUNNEL["dedup_drops"],
        "seen_drops": SAMPLE_FUNNEL["seen_drops"],
        "candidates": SAMPLE_FUNNEL["candidates"],
        "verdicts_pre_judge": SAMPLE_FUNNEL["verdicts_pre_judge"],
        "verdicts_post_judge": SAMPLE_FUNNEL["verdicts_post_judge"],
        "judge_self_rating": SAMPLE_FUNNEL["judge_self_rating"],
        "total_cost_usd": SAMPLE_FUNNEL["total_cost_usd"],
        "duration_s": SAMPLE_FUNNEL["duration_s"],
    }
    log_path.write_text(json.dumps(sample_log) + "\n")

    print(f"📝 Wrote {html_path}")
    print(f"📝 Wrote {json_path}")
    print(f"📝 Wrote {log_path}")
    print(f"🎨 Open the preview:   open {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
