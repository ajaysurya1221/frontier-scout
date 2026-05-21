#!/usr/bin/env python3
"""
Frontier Scout — Demo Mode.

One command that generates a polished sample briefing from seeded data —
no Slack, no AWS, no GitHub Actions setup needed. Lets anyone clone the repo
and see what the system produces in 60 seconds.

Outputs:
  demo/briefing.html         — Slack-style HTML preview of the threaded briefing
  demo/briefing.md           — the markdown briefing as it lands in the repo
  demo/judge-trace.md        — the judge's per-verdict decisions + veto reasons
  demo/quality-log.jsonl     — sample funnel + judge + retry stats
  demo/cost-breakdown.md     — observed-cost table by component

Run:
    python scripts/demo.py
    open demo/briefing.html

No API keys required. No network calls. Pure local rendering of seeded
content that matches what a real Scout run would produce.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REPO_ROOT = Path(__file__).parent.parent
DEMO_DIR = REPO_ROOT / "demo"


# ── Seeded sample verdicts ───────────────────────────────────────────────────
# These reflect the format and quality bar of real Scout output. The
# tool names are real; the verdicts are hand-crafted for the demo.

SAMPLE_DATE = "2026-05-21"
SAMPLE_VERDICTS = [
    {
        "tool_name": "anthropics/skills",
        "verdict": "adopt",
        "category": "tool",
        "soc2": "safe",
        "what": "Anthropic's official public repository of Agent Skills — reusable, composable capability modules for Claude-based agents.",
        "why_it_matters": "Skills primitives accelerate building agentic capabilities (retrieval, structured extraction, tool-use patterns) without reinventing plumbing, and carry implicit compatibility guarantees with Claude model updates.",
        "why_this_week": "Public release this week with broad surge in adoption across Claude Code, Codex and Cursor integrations.",
        "adoption_cost": "~2 hrs to audit + prototype one skill in an existing agent · low risk",
        "next_action": "Lab — clone, identify one skill applicable to document extraction, integrate into one LangGraph node, demo to the team within 1 sprint.",
        "source_url": "https://github.com/anthropics/skills",
        "severity": "critical",
        "readiness": 5,
        "_judge_decision": "keep",
        "_judge_reason": "Official Anthropic source, immediate stack-fit, low adoption cost, concrete next action with timebox.",
    },
    {
        "tool_name": "Gemini 3.5 Flash",
        "verdict": "trial",
        "category": "frontier_model",
        "soc2": "conditional",
        "what": "Google's new GA fast/cheap frontier model, deployed across Search and Gemini app at scale.",
        "why_it_matters": "Flash-tier pricing makes it a credible candidate for high-volume document classification where Sonnet cost dominates. GA-from-day-one signals production readiness; SOC2 conditional pending Vertex AI data residency confirmation.",
        "why_this_week": "Skipped preview and jumped straight to GA — Google is signaling production-confidence on the Flash tier.",
        "adoption_cost": "~3 hrs benchmark vs Sonnet on 50 classification samples · medium risk (verify Vertex training opt-out)",
        "next_action": "Evaluate — run head-to-head benchmark on document classification; check Vertex AI data-processing addendum for training opt-out before any prod data path.",
        "source_url": "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        "severity": "high",
        "readiness": 5,
        "_judge_decision": "keep",
        "_judge_reason": "Major lab release; existing Gemini integration means low integration overhead; SOC2 caveat is correctly conservative.",
    },
    {
        "tool_name": "obra/superpowers",
        "verdict": "adopt",
        "category": "tool",
        "soc2": "conditional",
        "what": "Agentic skills framework + software development methodology already on our dev stack.",
        "why_it_matters": "Stack-direct hit. 10,577 stars this week signals a major version or surge — check if our pinned version is current and whether new skills are relevant to ongoing work.",
        "why_this_week": "Trending hard on GitHub this week (+10.5k stars in 7 days) — strong signal something changed.",
        "adoption_cost": "Already on the dev stack · upgrade audit is ~1 hr",
        "next_action": "Audit current pin against latest release; review changelog for breaking changes; bump version if compatible.",
        "source_url": "https://github.com/obra/superpowers",
        "severity": "high",
        "readiness": 4,
        "_judge_decision": "promote",
        "_judge_reason": "Stack-direct trending repo missed by the verdict-gen pass; clear adoption path because we already use it.",
        "_promoted_by_judge": True,
    },
    {
        "tool_name": "Forge (Guardrails for Agentic Tasks)",
        "verdict": "trial",
        "category": "orchestration",
        "soc2": "conditional",
        "what": "Open-source guardrail framework that lifts an 8B-model task-completion rate from 53% to 99% on agentic benchmarks via proposer + verifier loops.",
        "why_it_matters": "Reliability claim is compelling for domains where a hallucinated extraction or citation is a trust-killer. Complements deepeval already in the stack.",
        "adoption_cost": "~4-6 hrs to wrap one LangGraph node · medium risk (early-stage project, API may shift)",
        "next_action": "Lab — apply Forge guardrails to one agent node; compare output validity rate against baseline using deepeval; timebox to 4 hrs.",
        "source_url": "https://github.com/antoinezambelli/forge",
        "severity": "high",
        "readiness": 2,
        "_judge_decision": "keep",
        "_judge_reason": "Promising reliability mechanism with concrete lab hypothesis; SOC2 conditional captures the solo-dev early-stage risk.",
    },
    {
        "tool_name": "Qwen3.6-35B-A3B",
        "verdict": "assess",
        "category": "frontier_model",
        "soc2": "conditional",
        "what": "Alibaba open-weight multimodal MoE (35B total / 3B active), Apache-2.0, 5.8M downloads on HuggingFace.",
        "why_it_matters": "Apache-2.0 + MoE efficiency makes this interesting for self-hosted inference. 3B active params runs on smaller GPU instances. Alibaba provenance needs legal sign-off before any prod path.",
        "adoption_cost": "1-2 days to stand up on SageMaker for benchmarking · medium risk (legal review required)",
        "next_action": "Monitor 3 months — watch for independent evals on document-heavy tasks; revisit when self-host fallback is a real need.",
        "source_url": "https://huggingface.co/Qwen/Qwen3.6-35B-A3B",
        "severity": "standard",
        "readiness": 4,
        "_judge_decision": "keep",
        "_judge_reason": "Defensible 'assess' — provenance concern correctly captured; not urgent enough to promote.",
    },
    {
        "tool_name": "DeepSeek-V4-Pro",
        "verdict": "hold",
        "category": "frontier_model",
        "soc2": "blocked",
        "what": "DeepSeek open-weight frontier model, MIT license, 3.8M downloads on HuggingFace.",
        "why_it_matters": "Chinese AI lab with documented data-residency ambiguity and ongoing compliance scrutiny. Prior versions had telemetry questions never fully resolved.",
        "adoption_cost": "N/A — blocked on SOC2 and compliance grounds regardless of self-hosting posture.",
        "next_action": "Hold indefinitely. Revisit only if legal counsel explicitly clears it.",
        "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
        "severity": "standard",
        "readiness": 4,
        "_judge_decision": "keep",
        "_judge_reason": "Correctly SOC2-blocked; verdict's restraint is appropriate.",
    },
]

# Items the judge VETOED (would have been kept by verdict-gen but the
# judge struck them down) — visible in judge-trace.md so the value of
# the judge layer is concrete.
SAMPLE_VETOED = [
    {
        "tool_name": "LlamaIndex v0.14.22",
        "draft_verdict": "adopt",
        "veto_reason": "patch release of an already-adopted framework (55 sub-package lockfile bump). ADOPT bar requires a substantive API change or new capability; this is dependency hygiene.",
    },
    {
        "tool_name": "CISA AWS GovCloud Key Leak",
        "draft_verdict": "adopt",
        "veto_reason": "tool_name matches incident/breach pattern, not a tool/framework. The radar evaluates tools; security advisories belong in a different output channel.",
    },
]

SAMPLE_FUNNEL = {
    "items_scanned": 377,
    "dedup_drops": 22,
    "mem0_prior_drops": 5,
    "candidates": 350,
    "verdicts_pre_judge": 7,
    "verdicts_post_judge": 6,
    "vetoed": 2,
    "tier_adjusted": 0,
    "missed_recovered": 1,
    "policy_dropped": 0,
    "judge_self_rating": "high",
    "judge_summary": "Tight upstream pass — vetoed two noise items, promoted one stack-direct trending repo. SOC2 calls are conservative and well-reasoned.",
    "total_cost_usd": 0.31,
    "duration_s": 232.0,
}

COST_BREAKDOWN = [
    ("Sonnet score (250 candidates)", 0.146),
    ("Sonnet verdict (7 drafts)", 0.041),
    ("Opus judge (adaptive thinking)", 0.122),
    ("OpenAI embeddings (Mem0 prior + seed)", 0.001),
    ("**Total**", 0.310),
]


# ── Markdown renderers ───────────────────────────────────────────────────────

VERDICT_LABEL = {"adopt": "🟢 ADOPT", "trial": "🟡 TRIAL", "assess": "⚪ ASSESS", "hold": "🔴 HOLD"}
SOC2_LABEL = {"safe": "✅ SOC2-safe", "conditional": "⚠️ SOC2-conditional", "blocked": "❌ SOC2-blocked"}
CAT_LABEL = {
    "frontier_model": "🧠 Frontier Models",
    "orchestration": "🤖 Orchestration & Agents",
    "tool": "🛠️ Tools & Frameworks",
    "data": "📊 Data Ecosystem",
    "compute": "⚡ Compute & Hardware",
    "security": "🔐 Security & Compliance",
}
SEV_LABEL = {"critical": "🔥", "high": "⭐", "standard": "📌"}


def render_briefing_md() -> str:
    lines = [
        f"# Frontier Scout — Weekly Briefing · {SAMPLE_DATE}",
        f"> Scanned **{SAMPLE_FUNNEL['items_scanned']}** items · "
        f"**{SAMPLE_FUNNEL['candidates']}** considered after dedup + Mem0 prior-filter · "
        f"**{len(SAMPLE_VERDICTS)}** verdicts after RLAIF judge pass. "
        f"Run cost **${SAMPLE_FUNNEL['total_cost_usd']:.4f}** (cached). "
        f"Judge confidence: **{SAMPLE_FUNNEL['judge_self_rating']}**.",
        "",
        f"> _{SAMPLE_FUNNEL['judge_summary']}_",
        "",
    ]
    for v in SAMPLE_VERDICTS:
        sev = SEV_LABEL.get(v["severity"], "📌")
        readiness = v["readiness"]
        meter = "▰" * readiness + "▱" * (5 - readiness)
        lines += [
            f"### {sev} [{v['tool_name']}]({v['source_url']}) — {VERDICT_LABEL[v['verdict']]} "
            f"— {SAMPLE_DATE} — {CAT_LABEL[v['category']]} — {SOC2_LABEL[v['soc2']]}",
            f"**What**: {v['what']}",
            f"**Why it matters**: {v['why_it_matters']}",
        ]
        if v.get("why_this_week"):
            lines.append(f"**Why this week**: {v['why_this_week']}")
        lines += [
            f"**Adoption cost**: {v['adoption_cost']}",
            f"**Next action**: {v['next_action']}",
            f"**Readiness**: `{meter}` {readiness}/5",
            "",
        ]
    lines += [
        "---",
        "*Dig deeper: `evaluate <tool>` · Build skill: `lab <tool>` · Recall past verdicts: `recall <topic>`*",
    ]
    return "\n".join(lines)


def render_judge_trace_md() -> str:
    lines = [
        "# Judge Trace — RLAIF decisions",
        "",
        f"_Generated for {SAMPLE_DATE} demo briefing. Shows the Opus 4.7 judge's "
        f"per-draft decision (keep / veto / retier / promote) with rationale._",
        "",
        f"**Quality self-rating:** {SAMPLE_FUNNEL['judge_self_rating']}",
        f"**Summary:** {SAMPLE_FUNNEL['judge_summary']}",
        "",
        "## ✅ Kept verdicts",
        "",
    ]
    for v in SAMPLE_VERDICTS:
        decision = v.get("_judge_decision", "keep")
        reason = v.get("_judge_reason", "")
        promoted = " (promoted from missed pool)" if v.get("_promoted_by_judge") else ""
        lines += [
            f"### {v['tool_name']} → {decision.upper()}{promoted}",
            f"**Verdict:** {VERDICT_LABEL[v['verdict']]} · {SOC2_LABEL[v['soc2']]} · severity {SEV_LABEL.get(v['severity'])} · readiness {v['readiness']}/5",
            f"**Judge reason:** {reason}",
            "",
        ]
    lines += ["## ❌ Vetoed drafts", ""]
    for v in SAMPLE_VETOED:
        lines += [
            f"### {v['tool_name']} → VETOED (was draft `{v['draft_verdict']}`)",
            f"**Reason:** {v['veto_reason']}",
            "",
        ]
    lines += [
        "---",
        "_The judge layer turns the system from 'Sonnet's best guess' into "
        "'Sonnet's best guess, audited by Opus.' Vetoes you see here are noise "
        "that would have shipped without the judge._",
    ]
    return "\n".join(lines)


def render_cost_breakdown_md() -> str:
    lines = [
        "# Cost breakdown — single Scout run",
        "",
        "Observed numbers from the demo's seeded run. Real runs land in the same band.",
        "",
        "| Component | Cost (USD) |",
        "|---|---|",
    ]
    for component, cost in COST_BREAKDOWN:
        lines.append(f"| {component} | ${cost:.4f} |")
    lines += [
        "",
        "## Monthly extrapolation",
        "",
        "| Cadence | Runs/month | Monthly cost |",
        "|---|---|---|",
        "| Scout (weekly) | 4 | ~$1.24 |",
        "| Pulse (daily, mostly silent) | 30 | ~$0.30 |",
        "| Synthesizer (monthly Opus) | 1 | ~$0.10 |",
        "| Lambda interactivity (free tier) | — | <$0.10 |",
        "| **Total** | | **~$2 / month** |",
        "",
        "_Anthropic monthly spend cap recommended: **$30**._",
    ]
    return "\n".join(lines)


# ── HTML renderer (Slack-style preview) ──────────────────────────────────────

HTML_BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Frontier Scout — Demo Briefing</title>
<style>
:root {
  --bg: #f8f8f8;
  --card: #ffffff;
  --text: #1d1c1d;
  --muted: #616061;
  --border: #e1e1e1;
  --link: #1264a3;
  --code-bg: #f4ede4;
  --quote-border: #e1e1e1;
  --adopt: #36a64f;
  --trial: #f2c744;
  --assess: #9aa0a6;
  --hold: #d93025;
}
html, body { margin: 0; padding: 0; background: var(--bg); }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  color: var(--text);
  font-size: 15px;
  line-height: 1.46;
}
.wrap { max-width: 760px; margin: 32px auto; padding: 0 16px; }
header { margin-bottom: 24px; }
header h1 { font-size: 18px; margin: 0 0 4px 0; }
header .meta { color: var(--muted); font-size: 13px; }

.parent {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 20px 24px; margin-bottom: 16px;
}
.parent h2 { font-size: 22px; margin: 0 0 8px 0; }
.parent .stats { color: var(--muted); font-size: 14px; margin-bottom: 8px; }
.parent .sev-counts { color: var(--text); font-size: 14px; margin-bottom: 16px; }
.parent blockquote {
  border-left: 4px solid var(--quote-border); margin: 0 0 16px 0;
  padding: 4px 12px; color: var(--text); font-size: 14px;
}
.parent .tier-tldr { margin-top: 18px; }
.parent .tier-tldr h3 { font-size: 15px; margin: 12px 0 6px 0; }
.parent .tier-tldr ul { margin: 0; padding-left: 24px; }
.parent .tier-tldr li { padding: 2px 0; }
.parent .footer { color: var(--muted); font-size: 13px; margin-top: 16px;
                   padding-top: 12px; border-top: 1px solid var(--border); }

.thread-anchor {
  text-align: center; color: var(--muted); font-size: 13px;
  margin: 14px 0 8px 0;
}

.card {
  background: var(--card); border-radius: 8px;
  border-left: 4px solid var(--assess);
  margin-bottom: 12px; padding: 16px 20px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.card.adopt { border-left-color: var(--adopt); }
.card.trial { border-left-color: var(--trial); }
.card.assess { border-left-color: var(--assess); }
.card.hold { border-left-color: var(--hold); }

.card .head { font-size: 15px; }
.card .head a { color: var(--link); text-decoration: none; font-weight: 700; }
.card .head a:hover { text-decoration: underline; }
.card .badges { color: var(--muted); font-size: 13px; margin: 4px 0 10px 0; }
.card .what { font-style: italic; color: var(--text); margin-bottom: 12px; }
.card .field { margin: 8px 0; }
.card .field .label { font-weight: 700; }
.card .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
.card .meter { color: var(--muted); font-size: 13px; margin-top: 10px;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.card blockquote {
  border-left: 3px solid var(--quote-border); margin: 6px 0;
  padding: 2px 10px; font-size: 14px; color: var(--text);
}
.actions {
  display: flex; gap: 8px; margin-top: 14px; padding-top: 10px;
  border-top: 1px solid var(--border);
}
.btn {
  background: #f8f8f8; border: 1px solid var(--border); border-radius: 4px;
  padding: 6px 12px; font-size: 13px; color: var(--text); cursor: default;
}
.btn.primary { background: var(--adopt); color: white; border-color: var(--adopt); }

footer { color: var(--muted); font-size: 12px; text-align: center; margin: 24px 0; }
footer a { color: var(--link); }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>#frontier-scout · Slack preview</h1>
  <div class="meta">This is what the bot posts every Monday. Generated locally — no Slack workspace required.</div>
</header>
__PARENT__
__THREAD__
<footer>
  Generated by <code>scripts/demo.py</code> — open the file to regenerate with your own seeded data.<br>
  Hover any verdict card; the 🧪/📚/📊 actions are wired to AWS Lambda in real deployments.
</footer>
</div>
</body>
</html>
"""


def _keycap(n: int) -> str:
    keycaps = ["", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    return keycaps[n] if 1 <= n <= 10 else f"#{n}"


def render_parent_html() -> str:
    sev_counts = {"critical": 0, "high": 0, "standard": 0}
    for v in SAMPLE_VERDICTS:
        sev_counts[v["severity"]] = sev_counts.get(v["severity"], 0) + 1

    considered = SAMPLE_FUNNEL["items_scanned"] - SAMPLE_FUNNEL["dedup_drops"] - SAMPLE_FUNNEL["mem0_prior_drops"]

    tier_blocks = []
    counter = 0
    for tier in ["adopt", "trial", "assess", "hold"]:
        items = [v for v in SAMPLE_VERDICTS if v["verdict"] == tier]
        if not items:
            continue
        lines = [f'<h3>{VERDICT_LABEL[tier]} · {len(items)}</h3>', "<ul>"]
        for v in items:
            counter += 1
            cat_short = CAT_LABEL[v["category"]].split(" ", 1)[0]
            soc2_short = SOC2_LABEL[v["soc2"]].split(" ", 1)[0]
            sev = SEV_LABEL.get(v["severity"])
            lines.append(
                f'<li>{_keycap(counter)} {sev} <strong>{v["tool_name"]}</strong> '
                f'· {cat_short} · {soc2_short}</li>'
            )
        lines.append("</ul>")
        tier_blocks.append("\n".join(lines))

    return f"""
<div class="parent">
  <h2>📡 Frontier Scout — Weekly Briefing · {SAMPLE_DATE}</h2>
  <div class="stats">
    <strong>{SAMPLE_FUNNEL['items_scanned']}</strong> scanned ·
    <strong>{considered}</strong> considered ·
    <strong>{len(SAMPLE_VERDICTS)}</strong> shipped
  </div>
  <div class="stats">
    🤖 Judge: <strong>{SAMPLE_FUNNEL['judge_self_rating'].upper()}</strong> ·
    💰 ${SAMPLE_FUNNEL['total_cost_usd']:.4f} ·
    ⏱ {int(SAMPLE_FUNNEL['duration_s'])}s
  </div>
  <div class="sev-counts">
    🔥 <strong>{sev_counts['critical']}</strong> critical ·
    ⭐ <strong>{sev_counts['high']}</strong> high ·
    📌 <strong>{sev_counts['standard']}</strong> standard
  </div>

  <blockquote>🧠 <strong>Judge's read</strong><br>{SAMPLE_FUNNEL['judge_summary']}</blockquote>

  <div class="tier-tldr">
    <h3 style="text-align:center;color:var(--muted);">━━━━━━━━━━  TL;DR  ━━━━━━━━━━</h3>
    {chr(10).join(tier_blocks)}
  </div>

  <div class="footer">
    🧵 Full verdicts in thread →  react 🧪 to lab · 👍 worth it · 👎 skip
  </div>
</div>
"""


def render_card_html(num: int, v: dict) -> str:
    tier_css = v["verdict"]
    sev = SEV_LABEL.get(v["severity"], "📌")
    readiness = v["readiness"]
    meter = "▰" * readiness + "▱" * (5 - readiness)
    why_now = f'\n  <div class="field"><blockquote>📅 <strong>Why this week</strong><br>{v["why_this_week"]}</blockquote></div>' if v.get("why_this_week") else ""

    return f"""
<div class="card {tier_css}">
  <div class="head">{_keycap(num)} · {sev} <a href="{v['source_url']}">{v['tool_name']}</a></div>
  <div class="badges">{VERDICT_LABEL[v['verdict']]} · {CAT_LABEL[v['category']]} · {SOC2_LABEL[v['soc2']]}</div>
  <div class="what">{v['what']}</div>
  <div class="field"><span class="label">💡 Why it matters</span><br>{v['why_it_matters']}</div>{why_now}
  <div class="grid">
    <div><strong>⏱ Adoption</strong><br>{v['adoption_cost']}</div>
    <div><strong>▶ Next action</strong><br>{v['next_action']}</div>
  </div>
  <div class="meter">📊 Readiness <code>{meter}</code> {readiness}/5</div>
  <div class="actions">
    <button class="btn primary" disabled>🧪 Queue lab</button>
    <button class="btn" disabled>📚 Full evaluation</button>
    <button class="btn" disabled>📊 Compare</button>
  </div>
</div>
"""


def render_thread_html() -> str:
    blocks = []
    counter = 0
    for tier in ["adopt", "trial", "assess", "hold"]:
        items = [(i, v) for i, v in enumerate(SAMPLE_VERDICTS) if v["verdict"] == tier]
        if not items:
            continue
        blocks.append(
            f'<div class="thread-anchor">━━━━━━━━━━ {VERDICT_LABEL[tier]} · {len(items)} ━━━━━━━━━━</div>'
        )
        for _, v in items:
            counter += 1
            blocks.append(render_card_html(counter, v))
    return "\n".join(blocks)


def render_briefing_html() -> str:
    return HTML_BASE.replace("__PARENT__", render_parent_html()).replace("__THREAD__", render_thread_html())


# ── Quality log sample ───────────────────────────────────────────────────────

def render_quality_log_jsonl() -> str:
    record = {
        "ts": datetime(2026, 5, 21, 3, 30, tzinfo=timezone.utc).isoformat(),
        "component": "scout",
        **SAMPLE_FUNNEL,
        "slack_posted": True,
        "judge_used_fallback": False,
        "llm_retries_total": 0,
        "llm_retries_by_component": {},
    }
    return json.dumps(record) + "\n"


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "briefing.md": render_briefing_md(),
        "briefing.html": render_briefing_html(),
        "judge-trace.md": render_judge_trace_md(),
        "cost-breakdown.md": render_cost_breakdown_md(),
        "quality-log.jsonl": render_quality_log_jsonl(),
    }
    for name, content in files.items():
        path = DEMO_DIR / name
        path.write_text(content)
        print(f"✅ {path.relative_to(REPO_ROOT)}  ({len(content):,} chars)")

    print()
    print(f"🎨  Open the Slack-style preview:  open {DEMO_DIR / 'briefing.html'}")
    print(f"📄  Read the briefing markdown:    cat {DEMO_DIR / 'briefing.md'}")
    print(f"⚖️   See judge decisions:           cat {DEMO_DIR / 'judge-trace.md'}")
    print(f"💰  Cost breakdown:                cat {DEMO_DIR / 'cost-breakdown.md'}")


if __name__ == "__main__":
    main()
