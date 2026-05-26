"""Static report rendering and seeded demo data for Frontier Scout."""
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAMPLE_DATE = "2026-05-21"

SAMPLE_VERDICTS: list[dict[str, Any]] = [
    {
        "tool_name": "anthropics/skills",
        "verdict": "adopt",
        "category": "skill",
        "risk": "low",
        "fit": "high",
        "what": "Anthropic's official repo of reusable Skill bundles for AI coding agents.",
        "why_this_week": "A new batch expanded the catalogue beyond the first few coding workflows.",
        "why_it_matters": "If you already work inside Claude Code, Codex, or Cursor, reusable skill bundles turn repeat prompts into durable operating procedure.",
        "adoption_cost": "~10 min to inspect one skill and test it in a non-production repo. Low risk.",
        "next_action": "Run a local lab on one skill, then install only the workflow you would actually use this week.",
        "source_url": "https://github.com/anthropics/skills",
        "severity": "critical",
        "readiness": 5,
        "tags": ["skill", "claude-code", "agentic-coding"],
    },
    {
        "tool_name": "modelcontextprotocol/servers",
        "verdict": "trial",
        "category": "mcp_server",
        "risk": "medium",
        "fit": "high",
        "what": "Reference MCP servers that connect AI agents to databases, filesystems, browser tools, and developer APIs.",
        "why_this_week": "MCP adoption is accelerating across coding agents, and reference servers are becoming the default integration path.",
        "why_it_matters": "Teams adopting AI coding agents need tool access that is explicit, auditable, and easy to revoke. MCP is becoming that contract.",
        "adoption_cost": "~30 min to test one read-only server with throwaway credentials. Medium risk until permissions are reviewed.",
        "next_action": "Trial one read-only MCP server against a sandbox project and document the permission boundary.",
        "source_url": "https://github.com/modelcontextprotocol/servers",
        "severity": "high",
        "readiness": 4,
        "tags": ["mcp", "agent-tools", "developer-tools"],
    },
    {
        "tool_name": "browser-use/browser-use",
        "verdict": "trial",
        "category": "agent_framework",
        "risk": "medium",
        "fit": "medium",
        "what": "Python framework for browser-driving agents powered by Playwright and LLM tool calls.",
        "why_this_week": "Recent structured-output support makes browser tasks easier to evaluate and retry.",
        "why_it_matters": "Research, QA, and competitive-intel workflows often need real browser interaction. This can replace brittle one-off scripts when tested carefully.",
        "adoption_cost": "~45 min to lab-test on a public site. Medium risk because browser automation is dependency-heavy.",
        "next_action": "Lab-test one public browsing workflow and compare success rate, cost, and maintenance against a plain Playwright script.",
        "source_url": "https://github.com/browser-use/browser-use",
        "severity": "high",
        "readiness": 4,
        "tags": ["browser", "agent-framework", "automation"],
    },
    {
        "tool_name": "Qwen/Qwen3-Coder-30B",
        "verdict": "assess",
        "category": "model_drop",
        "risk": "medium",
        "fit": "low",
        "what": "Open-weight coding model aimed at local or self-hosted code generation workflows.",
        "why_this_week": "Fresh model release with enough community attention to watch independent evals closely.",
        "why_it_matters": "Hosted frontier models still win for many teams, but local coding models can matter for privacy, latency, and fallback paths.",
        "adoption_cost": "~2 hrs to benchmark if you already have GPU capacity; otherwise not worth the infrastructure work yet.",
        "next_action": "Monitor independent coding-agent evals for 30 days before spending integration time.",
        "source_url": "https://huggingface.co/Qwen/Qwen3-Coder-30B",
        "severity": "standard",
        "readiness": 3,
        "tags": ["model-drop", "coding-model", "local-inference"],
    },
    {
        "tool_name": "deepseek-ai/DeepSeek-V4-Pro",
        "verdict": "hold",
        "category": "model_drop",
        "risk": "high",
        "fit": "low",
        "what": "Large open-weight reasoning model with a footprint beyond a normal laptop or small CI runner.",
        "why_this_week": "High-visibility release, but size and operational requirements make it a poor first trial for most teams.",
        "why_it_matters": "It is important ecosystem signal, not an immediate adoption candidate for a lean engineering team.",
        "adoption_cost": "Weekend-scale GPU setup plus ongoing compute. High risk unless a real self-hosting need exists.",
        "next_action": "Hold until smaller quantized variants and credible independent evals are available.",
        "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
        "severity": "standard",
        "readiness": 4,
        "tags": ["model-drop", "reasoning", "large-model"],
    },
]

SAMPLE_FUNNEL: dict[str, Any] = {
    "items_scanned": 377,
    "dedup_drops": 22,
    "seen_drops": 5,
    "candidates": 350,
    "scored_above_threshold": 19,
    "verdicts_pre_judge": 8,
    "verdicts_post_judge": len(SAMPLE_VERDICTS),
    "judge_self_rating": "high",
    "judge_summary": "Tight upstream pass: vetoed patch-release noise, kept source-backed verdicts, and preserved conservative risk calls.",
    "total_cost_usd": 0.31,
    "duration_s": 232.4,
}

VERDICT_LABEL = {
    "adopt": "ADOPT",
    "trial": "TRIAL",
    "assess": "ASSESS",
    "hold": "HOLD",
}

CATEGORY_LABEL = {
    "skill": "Skill",
    "mcp_server": "MCP Server",
    "agent_framework": "Agent Framework",
    "dev_tool": "Dev Tool",
    "model_drop": "Model Drop",
}

RISK_LABEL = {
    "low": "low risk",
    "medium": "medium risk",
    "high": "high risk",
}

TIER_HINT = {
    "adopt": "Use now",
    "trial": "Test next",
    "assess": "Watch closely",
    "hold": "Do not spend time yet",
}


def load_verdict_file(path: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return SAMPLE_DATE, payload, {}
    return (
        str(payload.get("date") or SAMPLE_DATE),
        list(payload.get("verdicts") or []),
        dict(payload.get("funnel") or {}),
    )


def render_html(
    verdicts: list[dict[str, Any]],
    *,
    date: str = SAMPLE_DATE,
    funnel: dict[str, Any] | None = None,
    include_trials: bool = True,
) -> str:
    funnel = {**SAMPLE_FUNNEL, **(funnel or {})}
    grouped = _group_by_tier(verdicts)
    cards = "\n".join(_render_card(v, i + 1) for i, v in enumerate(verdicts))
    trial_section = _render_trial_section_html() if include_trials else ""
    summary = " · ".join(
        f"{VERDICT_LABEL[tier]} {len(grouped[tier])}"
        for tier in ("adopt", "trial", "assess", "hold")
        if grouped[tier]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Frontier Scout Radar · {date}</title>
<style>
:root {{
  color-scheme: light;
  --ink: #17202a;
  --muted: #5f6b7a;
  --line: #d9e1ea;
  --paper: #fbfcfe;
  --panel: #ffffff;
  --adopt: #137a4b;
  --trial: #9a6700;
  --assess: #52616f;
  --hold: #b42318;
  --accent: #2454d6;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--paper);
  color: var(--ink);
  line-height: 1.55;
}}
main {{ max-width: 1120px; margin: 0 auto; padding: 40px 22px 56px; }}
.hero {{ border-bottom: 1px solid var(--line); padding-bottom: 26px; }}
.kicker {{ color: var(--accent); font-weight: 700; text-transform: uppercase; letter-spacing: .08em; font-size: 12px; }}
h1 {{ margin: 8px 0 10px; font-size: clamp(34px, 5vw, 64px); line-height: 1.02; letter-spacing: 0; }}
.promise {{ max-width: 760px; color: var(--muted); font-size: 19px; }}
.metrics {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 26px 0 0; }}
.metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
.metric b {{ display: block; font-size: 20px; }}
.metric span {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
.judge {{ margin-top: 16px; max-width: 900px; color: var(--muted); }}
.section-title {{ margin: 34px 0 10px; display: flex; justify-content: space-between; gap: 16px; align-items: end; }}
.section-title h2 {{ margin: 0; font-size: 24px; }}
.section-title p {{ margin: 0; color: var(--muted); }}
.cards {{ display: grid; gap: 14px; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-left: 5px solid var(--assess); border-radius: 8px; padding: 18px; }}
.card.adopt {{ border-left-color: var(--adopt); }}
.card.trial {{ border-left-color: var(--trial); }}
.card.assess {{ border-left-color: var(--assess); }}
.card.hold {{ border-left-color: var(--hold); }}
.card-head {{ display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }}
.tier {{ font-weight: 800; font-size: 12px; letter-spacing: .08em; }}
.adopt .tier {{ color: var(--adopt); }}
.trial .tier {{ color: var(--trial); }}
.assess .tier {{ color: var(--assess); }}
.hold .tier {{ color: var(--hold); }}
.meta {{ color: var(--muted); font-size: 13px; }}
h3 {{ margin: 7px 0 8px; font-size: 22px; letter-spacing: 0; }}
a {{ color: var(--accent); text-decoration: none; }}
.what {{ font-size: 16px; margin: 0 0 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }}
.field {{ border-top: 1px solid var(--line); padding-top: 10px; }}
.field b {{ display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 2px; }}
code {{ background: #eef2f7; border: 1px solid #dfe6ef; border-radius: 5px; padding: 1px 5px; }}
footer {{ color: var(--muted); margin-top: 34px; padding-top: 20px; border-top: 1px solid var(--line); font-size: 13px; }}
@media (max-width: 760px) {{
  main {{ padding-top: 28px; }}
  .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <section class="hero">
    <div class="kicker">Frontier Scout · Local AI Radar · {date}</div>
    <h1>Know which AI tools are worth trying this week.</h1>
    <p class="promise">A local briefing for AI engineers and technical leaders: source-backed adoption receipts with verdict, risk, stack fit, adoption cost, and the next lab test. No SaaS account. No hosted telemetry. Bring your own API key.</p>
    <div class="metrics">
      <div class="metric"><b>{funnel.get("items_scanned", 0)}</b><span>scanned</span></div>
      <div class="metric"><b>{funnel.get("candidates", 0)}</b><span>considered</span></div>
      <div class="metric"><b>{len(verdicts)}</b><span>verdicts</span></div>
      <div class="metric"><b>${float(funnel.get("total_cost_usd", 0)):.2f}</b><span>run cost</span></div>
      <div class="metric"><b>{funnel.get("judge_self_rating", "n/a")}</b><span>judge</span></div>
    </div>
    <p class="judge"><strong>Summary:</strong> {summary or "No shipped verdicts."} · {funnel.get("judge_summary", "")}</p>
  </section>
  <section>
    <div class="section-title">
      <h2>Adoption receipts</h2>
      <p>ADOPT / TRIAL / ASSESS / HOLD</p>
    </div>
    <div class="cards">
      {cards}
    </div>
  </section>{trial_section}
  <footer>
    Generated locally by <code>frontier-scout demo</code>. Each receipt preserves source provenance; run labs before installing anything in production.
  </footer>
</main>
</body>
</html>
"""


def render_markdown(
    verdicts: list[dict[str, Any]],
    *,
    date: str = SAMPLE_DATE,
    funnel: dict[str, Any] | None = None,
    include_trials: bool = True,
) -> str:
    funnel = {**SAMPLE_FUNNEL, **(funnel or {})}
    lines = [
        f"# Frontier Scout Radar - {date}",
        "",
        (
            f"Scanned **{funnel.get('items_scanned', 0)}** items, considered "
            f"**{funnel.get('candidates', 0)}**, shipped **{len(verdicts)}** verdicts. "
            f"Estimated run cost: **${float(funnel.get('total_cost_usd', 0)):.2f}**."
        ),
        "",
        f"> {funnel.get('judge_summary', '')}",
        "",
    ]
    for v in verdicts:
        tier = VERDICT_LABEL.get(v.get("verdict"), str(v.get("verdict", "")).upper())
        category = CATEGORY_LABEL.get(v.get("category"), v.get("category", "tool"))
        risk = RISK_LABEL.get(v.get("risk"), v.get("risk", "risk unknown"))
        fit = (v.get("fit") or "universal").upper()
        lines.extend(
            [
                f"## {tier} receipt: [{v.get('tool_name')}]({v.get('source_url')})",
                "",
                f"**Meta:** {category} · {risk} · fit {fit} · readiness {v.get('readiness', 'n/a')}/5",
                "",
                f"**What:** {v.get('what', '')}",
                "",
                f"**Why it matters:** {v.get('why_it_matters', '')}",
                "",
                f"**Why this week:** {v.get('why_this_week') or 'No specific timing signal.'}",
                "",
                f"**Adoption cost:** {v.get('adoption_cost', '')}",
                "",
                f"**Next action:** {v.get('next_action', '')}",
                "",
            ]
        )
    trials = _trial_summaries() if include_trials else []
    if trials:
        lines.extend(["## Adoption Firewall trials", ""])
        for trial in trials:
            lines.extend(
                [
                    f"- **{trial.get('tool_name')}**: {str(trial.get('decision') or trial.get('status') or 'unknown').upper()} "
                    f"({trial.get('requested_action') or 'trial'})",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(
    output_dir: Path,
    verdicts: list[dict[str, Any]],
    *,
    date: str = SAMPLE_DATE,
    funnel: dict[str, Any] | None = None,
    include_trials: bool = True,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "briefing.html"
    md_path = output_dir / "briefing.md"
    json_path = output_dir / "verdicts.json"
    log_path = output_dir / "quality-log.jsonl"
    cost_path = output_dir / "cost-breakdown.md"
    judge_path = output_dir / "judge-trace.md"

    payload = {"date": date, "funnel": {**SAMPLE_FUNNEL, **(funnel or {})}, "verdicts": verdicts}
    html_path.write_text(render_html(verdicts, date=date, funnel=funnel, include_trials=include_trials))
    md_path.write_text(render_markdown(verdicts, date=date, funnel=funnel, include_trials=include_trials))
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    log_path.write_text(json.dumps({"ts": f"{date}T00:00:00+00:00", "component": "demo", **payload["funnel"]}) + "\n")
    cost_path.write_text(render_cost_breakdown(payload["funnel"]))
    judge_path.write_text(render_judge_trace(verdicts, payload["funnel"]))
    return {
        "html": html_path,
        "markdown": md_path,
        "json": json_path,
        "quality_log": log_path,
        "cost": cost_path,
        "judge": judge_path,
    }


def write_demo(output_dir: Path) -> dict[str, Path]:
    return write_report(output_dir, SAMPLE_VERDICTS, date=SAMPLE_DATE, funnel=SAMPLE_FUNNEL, include_trials=False)


def render_cost_breakdown(funnel: dict[str, Any]) -> str:
    total = float(funnel.get("total_cost_usd", 0))
    return f"""# Cost breakdown - seeded demo run

The demo is offline and free. These numbers show the expected shape of a live weekly scan.

| Component | Demo estimate |
|---|---:|
| Source fetch + dedupe | $0.00 |
| Sonnet score pass | $0.15 |
| Sonnet verdict pass | $0.04 |
| Optional Opus judge | $0.12 |
| **Total** | **${total:.2f}** |

Default posture: BYO API key, local files, no hosted service. A weekly scan should sit comfortably in a small personal Anthropic budget.
"""


def render_judge_trace(verdicts: list[dict[str, Any]], funnel: dict[str, Any]) -> str:
    lines = [
        "# Judge trace - seeded demo",
        "",
        f"Quality self-rating: **{funnel.get('judge_self_rating', 'n/a')}**",
        "",
        f"> {funnel.get('judge_summary', '')}",
        "",
        "## Shipped verdicts",
        "",
    ]
    for v in verdicts:
        tier = VERDICT_LABEL.get(v.get("verdict"), str(v.get("verdict", "")).upper())
        lines.append(
            f"- **{v.get('tool_name')}** -> {tier}; readiness {v.get('readiness', 'n/a')}/5; risk {v.get('risk', 'n/a')}."
        )
    lines.extend(
        [
            "",
            "## What the judge protects against",
            "",
            "- Patch-release noise promoted as strategy.",
            "- Security incidents mislabeled as tools.",
            "- Source URLs that do not match the discovered item.",
            "- ADOPT verdicts without enough readiness evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def _group_by_tier(verdicts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {tier: [] for tier in ("adopt", "trial", "assess", "hold")}
    for v in verdicts:
        grouped.setdefault(str(v.get("verdict")), []).append(v)
    return grouped


def _render_card(v: dict[str, Any], index: int) -> str:
    tier = str(v.get("verdict", "assess"))
    label = VERDICT_LABEL.get(tier, tier.upper())
    category = CATEGORY_LABEL.get(v.get("category"), v.get("category", "Tool"))
    risk = RISK_LABEL.get(v.get("risk"), v.get("risk", "risk unknown"))
    fit = (v.get("fit") or "universal").upper()
    readiness = int(v.get("readiness") or 0)
    meter = "[" + ("#" * readiness).ljust(5, "-") + "]"
    why_now = v.get("why_this_week") or "No specific timing signal."
    return f"""<article class="card {tier}">
  <div class="card-head">
    <span class="tier">{index:02d} · {label}</span>
    <span class="meta">{category} · {risk} · fit {fit} · readiness <code>{meter}</code></span>
  </div>
  <h3><a href="{_esc_attr(v.get('source_url', '#'))}" rel="noopener">{_esc(v.get('tool_name', 'Unknown tool'))}</a></h3>
  <p class="what">{_esc(v.get('what', ''))}</p>
  <div class="grid">
    <div class="field"><b>Why it matters</b>{_esc(v.get('why_it_matters', ''))}</div>
    <div class="field"><b>Why this week</b>{_esc(why_now)}</div>
    <div class="field"><b>Adoption cost</b>{_esc(v.get('adoption_cost', ''))}</div>
    <div class="field"><b>Next action</b>{_esc(v.get('next_action', ''))}</div>
  </div>
  <p class="meta"><strong>{TIER_HINT.get(tier, "Review")}</strong> · provenance: {_esc(v.get('source_url', ''))}</p>
</article>"""


def _render_trial_section_html() -> str:
    trials = _trial_summaries()
    if not trials:
        return ""
    rows = "\n".join(
        f"""<article class="card trial">
  <div class="card-head">
    <span class="tier">TRIAL</span>
    <span class="meta">{_esc(trial.get('requested_action') or 'trial')} · {_esc(trial.get('status') or 'unknown')}</span>
  </div>
  <h3>{_esc(trial.get('tool_name'))}</h3>
  <p class="what">Decision: <strong>{_esc(str(trial.get('decision') or 'pending').upper())}</strong></p>
  <p class="meta">Recorded locally at {_esc(trial.get('created_at'))}</p>
</article>"""
        for trial in trials
    )
    return f"""
  <section>
    <div class="section-title">
      <h2>Adoption Firewall trials</h2>
      <p>Local try-before-trust receipts</p>
    </div>
    <div class="cards">
      {rows}
    </div>
  </section>"""


def _trial_summaries() -> list[dict[str, Any]]:
    try:
        from .store import list_trial_summaries

        return list_trial_summaries(limit=8)
    except Exception:
        return []


def _esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _esc_attr(value: Any) -> str:
    return _esc(value).replace('"', "&quot;")
