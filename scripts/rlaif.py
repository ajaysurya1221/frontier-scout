#!/usr/bin/env python3
"""RLAIF harness — Reinforcement Learning via AI Feedback.

Frontier Scout's selling point is *custom-fit scouting without missing a pin*.
The failure mode a real user hit was the opposite: generic web frameworks
(FastAPI, Flask, …) leaking into the AI-tools feed. Stream 2 added a two-layer
guardrail (rubric + deterministic backstop). This harness is the instrument
that *proves* the guardrail holds against live data and drives the
reinforcement loop:

    live scout  →  Opus scope-and-quality audit  →  false-positive report
                →  (operator tightens rubric/backstop)  →  rerun

"Reinforcement" here is human-in-the-loop with an AI judge: Claude Opus reads
each surfaced verdict and rules whether it is genuinely AI-native and whether
its fit/risk reasoning is grounded. The operator (the agent running this loop)
tightens ``scripts/prompts.py`` / ``scripts/tools.py`` / ``frontier_scout.scout``
when the judge flags a leak, then reruns. The loop is *satisfied* when two
consecutive cycles surface zero scope false-positives.

Safety:
  * Hard USD cap (``RLAIF_USD_CAP``, default $60). Every cycle prints the
    running tally; the harness refuses to start a new cycle once the cap is
    crossed. Cost is read from the real ledger filtered to this session's
    run-id, so reruns accumulate honestly.
  * Real keys are loaded from ``.env.local`` (presence only — never echoed).
  * No key is ever printed; only provider *name* and token counts surface.

Usage:
    python scripts/rlaif.py            # one live cycle, append to report
    python scripts/rlaif.py --cycles 3 # up to 3 cycles (stops early if clean)
    python scripts/rlaif.py --dry-run  # plumbing only, no spend (CI-safe)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Session run-id: every LLM call this process makes is tagged with it so the
# cumulative-spend reader can sum exactly this RLAIF session (across reruns the
# operator keeps the same id by exporting RLAIF_SESSION).
_SESSION = os.environ.get("RLAIF_SESSION") or f"rlaif-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:6]}"
os.environ["RLAIF_SESSION"] = _SESSION
os.environ["GITHUB_RUN_ID"] = _SESSION  # cost_tracker tags every call with this

_DEFAULT_CAP = float(os.environ.get("RLAIF_USD_CAP", "60"))
_REPORT_PATH = _REPO_ROOT / "demo" / "rlaif-report.md"


# ── Cumulative spend (this RLAIF session only) ───────────────────────────────


def _session_spend() -> float:
    """Sum every ledger entry whose run_id belongs to this RLAIF session."""
    from cost_tracker import LEDGER

    if not LEDGER.exists():
        return 0.0
    total = 0.0
    with LEDGER.open() as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("run_id") == _SESSION:
                total += float(rec.get("cost_usd") or 0.0)
    return total


# ── The scope-and-quality audit (Opus as judge) ──────────────────────────────

AUDIT_TOOL = {
    "name": "audit_verdicts",
    "description": (
        "Audit a list of Frontier Scout verdicts for an AI-ADOPTION RADAR. "
        "For every verdict decide two things independently: (1) is it IN SCOPE "
        "— i.e. genuinely AI-NATIVE (an AI/agent/LLM/MCP/RAG tool, an AI model "
        "drop, or a release that adds a first-class AI/agent capability)? A "
        "general-purpose web framework, HTTP client, ORM, database, or "
        "build/lint tool is NOT in scope and counts as a scope FALSE POSITIVE "
        "— even when it appears in the user's stack. (2) Is the verdict QUALITY "
        "sound — fit reasoning grounded in the item (not invented), risk tier "
        "sane, not a re-announcement of an old release, tool actually exists?"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "tool_name": {"type": "string"},
                        "in_scope": {
                            "type": "boolean",
                            "description": "True iff genuinely AI-native / in radar scope.",
                        },
                        "scope_reason": {"type": "string"},
                        "quality_ok": {
                            "type": "boolean",
                            "description": "True iff fit/risk/reasoning are grounded and sound.",
                        },
                        "quality_issue": {
                            "type": "string",
                            "description": "Empty when quality_ok is true.",
                        },
                    },
                    "required": [
                        "index",
                        "tool_name",
                        "in_scope",
                        "scope_reason",
                        "quality_ok",
                        "quality_issue",
                    ],
                },
            },
            "overall_rating": {
                "type": "string",
                "enum": ["excellent", "good", "needs_work", "failing"],
            },
            "summary": {"type": "string"},
            "rubric_recommendation": {
                "type": "string",
                "description": (
                    "If any scope false-positive or quality issue exists, the "
                    "concrete rubric/backstop change you recommend. Empty if clean."
                ),
            },
        },
        "required": ["assessments", "overall_rating", "summary", "rubric_recommendation"],
    },
}

_AUDIT_SYSTEM = (
    "You are Claude Opus acting as the strict RLAIF judge for Frontier Scout, a "
    "LOCAL-FIRST AI-ADOPTION RADAR. The radar's promise is to surface the best "
    "custom-fit AI tools, MCP servers, agent frameworks, and model drops for a "
    "developer's repo WITHOUT MISSING A PIN — and without polluting the feed "
    "with generic infrastructure.\n\n"
    "A real user previously saw FastAPI and other generic web frameworks in the "
    "AI-tools feed. That is the canonical FALSE POSITIVE you are guarding "
    "against. Be strict on scope but fair: a web framework release that adds a "
    "first-class MCP/agent/LLM endpoint IS in scope; the framework merely "
    "appearing in the user's stack is NOT a reason to keep it.\n\n"
    "CALIBRATION — read carefully. These verdicts were generated from LIVE feeds "
    "(RSS, GitHub releases, Hacker News) dated within the last 7 days. They are "
    "almost certainly MORE RECENT than your training cutoff. Therefore:\n"
    "  • DO NOT flag a verdict as a quality issue merely because you don't "
    "recognise the release, the version number looks higher than you remember, "
    "or the model/repo is unfamiliar. Assume the item is real — it came from a "
    "real feed. You are not a fact-checker for release existence.\n"
    "  • DO flag QUALITY issues that are verifiable from the verdict text ALONE: "
    "(a) FIT OVERREACH — the reasoning ASSUMES the user has adopted a tool that "
    "the stack profile does not contain (e.g. asserts 'pydantic-ai is in your "
    "stack' / 'you use Claude Code daily' as fact); (b) internal contradiction; "
    "(c) re-announcement of an old release framed as new; (d) no concrete next "
    "action; (e) marketing voice with unfalsifiable claims.\n"
    "  • DO NOT flag fit overreach when the verdict EXPLICITLY DISCLOSES the "
    "non-match and frames relevance conditionally — e.g. 'pydantic-ai (not "
    "detected in your stack — you have pydantic, a separate package); if you've "
    "adopted it, patch now'. That is exactly the honest, grounded behavior the "
    "radar is supposed to produce: surfacing a real adjacent release WITHOUT "
    "missing a pin, while being truthful that adoption is unconfirmed. Reward "
    "it; do not penalise it. Only flag when the prose treats the absent tool as "
    "already-in-use without that disclosure.\n"
    "Scope and fit-grounding are your mandate; release-existence trivia is not.\n\n"
    "You MUST call the audit_verdicts tool. Do not answer in prose."
)


def _audit_verdicts(verdicts: list[dict], stack_profile: dict | None) -> tuple[dict, float]:
    """Run the Opus scope-and-quality audit over final verdicts."""
    from cost_tracker import log_call
    from llm_client import call_with_retry

    from frontier_scout.providers import DEEP, first_tool_use, resolve_provider

    if not verdicts:
        return (
            {
                "assessments": [],
                "overall_rating": "good",
                "summary": "No verdicts to audit (empty live scan).",
                "rubric_recommendation": "",
            },
            0.0,
        )

    lines = []
    for i, v in enumerate(verdicts):
        lines.append(
            f"[verdict {i}] {v.get('tool_name')} — verdict={v.get('verdict')} "
            f"category={v.get('category')} risk={v.get('risk')} fit={v.get('fit') or '—'} "
            f"tags={v.get('tags') or []}\n"
            f"  what: {v.get('what')}\n"
            f"  why_it_matters: {v.get('why_it_matters')}\n"
            f"  source_url: {v.get('source_url')}"
        )
    block = "\n\n".join(lines)

    profile_note = ""
    if stack_profile:
        profile_note = f"\n\nThe user's stack (for fit context): {json.dumps(stack_profile)[:1500]}\n"

    provider = resolve_provider()
    model_id = provider.model(DEEP)
    resp = call_with_retry(
        provider,
        "rlaif-audit",
        model=model_id,
        max_tokens=4000,
        system=_AUDIT_SYSTEM,
        tools=[AUDIT_TOOL],
        tool_choice={"type": "tool", "name": "audit_verdicts"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Audit these {len(verdicts)} live verdicts for the AI-adoption "
                    f"radar.{profile_note}\n\n{block}"
                ),
            }
        ],
    )
    cost = log_call("rlaif-audit", model_id, resp.usage)
    tool_use = first_tool_use(resp.content)
    if tool_use is None:
        return (
            {
                "assessments": [],
                "overall_rating": "failing",
                "summary": "Audit judge emitted no structured tool call.",
                "rubric_recommendation": "Re-run; provider hiccup suspected.",
            },
            cost,
        )
    result = dict(tool_use.input)
    result.setdefault("assessments", [])
    result.setdefault("overall_rating", "needs_work")
    result.setdefault("summary", "")
    result.setdefault("rubric_recommendation", "")
    return result, cost


# ── Stack profile for this repo (real fit context) ───────────────────────────


def _stack_profile() -> dict | None:
    try:
        from frontier_scout.profile import build_scout_profile, stack_from_profile

        profile = build_scout_profile(_REPO_ROOT, scan_imports=False)
        return stack_from_profile(profile)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️  Could not build stack profile: {exc}")
        return None


# ── One cycle ─────────────────────────────────────────────────────────────────


def run_cycle(cycle_num: int, *, dry_run: bool) -> dict:
    """Run one scout→audit cycle and return a structured cycle record."""
    import scout as scout_mod

    started = datetime.now(UTC)
    print(f"\n{'━' * 70}\n  RLAIF cycle {cycle_num}  ·  session {_SESSION}\n{'━' * 70}")

    stack_profile = None if dry_run else _stack_profile()
    scan = scout_mod.run_scan(stack_profile=stack_profile, dry_run=dry_run)
    verdicts = list(scan.verdicts)
    print(f"  Scan: {len(verdicts)} verdicts · ${scan.cost_usd:.4f} · {scan.duration_s}s")

    if dry_run:
        audit = {
            "assessments": [
                {
                    "index": i,
                    "tool_name": v.get("tool_name", "?"),
                    "in_scope": True,
                    "scope_reason": "dry-run stub",
                    "quality_ok": True,
                    "quality_issue": "",
                }
                for i, v in enumerate(verdicts)
            ],
            "overall_rating": "good",
            "summary": "Dry-run cycle — no live audit performed.",
            "rubric_recommendation": "",
        }
        audit_cost = 0.0
    else:
        audit, audit_cost = _audit_verdicts(verdicts, stack_profile)

    assessments = audit.get("assessments", [])
    scope_fps = [a for a in assessments if not a.get("in_scope", True)]
    quality_issues = [a for a in assessments if not a.get("quality_ok", True)]

    print(
        f"  Audit ({audit.get('overall_rating')}): "
        f"{len(scope_fps)} scope false-positive(s), "
        f"{len(quality_issues)} quality issue(s) · ${audit_cost:.4f}"
    )
    for fp in scope_fps:
        print(f"    ✗ SCOPE  {fp.get('tool_name')}: {fp.get('scope_reason')}")
    for q in quality_issues:
        print(f"    ⚠ QUAL   {q.get('tool_name')}: {q.get('quality_issue')}")

    return {
        "cycle": cycle_num,
        "started": started.isoformat(),
        "verdicts": verdicts,
        "scan_cost_usd": round(scan.cost_usd, 6),
        "audit_cost_usd": round(audit_cost, 6),
        "audit": audit,
        "scope_false_positives": scope_fps,
        "quality_issues": quality_issues,
        "clean": not scope_fps and not quality_issues,
    }


# ── Report ──────────────────────────────────────────────────────────────────


def write_report(cycles: list[dict], *, cap: float, spend: float, satisfied: bool) -> Path:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append("# RLAIF Report — Frontier Scout AI-radar reinforcement\n")
    lines.append(
        "_Reinforcement Learning via AI Feedback. Claude Opus audits each live "
        "scout for scope discipline (no generic frameworks in the AI feed) and "
        "verdict quality. The loop is satisfied when two consecutive cycles "
        "surface zero scope false-positives._\n"
    )
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Session:** `{_SESSION}`")
    lines.append(f"- **Cycles run:** {len(cycles)}")
    lines.append(f"- **Budget cap:** ${cap:.2f}")
    lines.append(f"- **Session spend:** ${spend:.4f}")
    status = (
        "✅ SATISFIED — zero scope false-positives sustained"
        if satisfied
        else "⏳ in progress / needs another pass"
    )
    lines.append(f"- **Status:** {status}\n")

    for c in cycles:
        lines.append(f"\n## Cycle {c['cycle']}\n")
        audit = c["audit"]
        lines.append(f"- Rating: **{audit.get('overall_rating')}**")
        lines.append(f"- Verdicts surfaced: {len(c['verdicts'])}")
        lines.append(f"- Scope false-positives: {len(c['scope_false_positives'])}")
        lines.append(f"- Quality issues: {len(c['quality_issues'])}")
        lines.append(f"- Cost: scan ${c['scan_cost_usd']:.4f} + audit ${c['audit_cost_usd']:.4f}")
        if audit.get("summary"):
            lines.append(f"\n> {audit['summary']}\n")
        if c["scope_false_positives"]:
            lines.append("\n**Scope false-positives (would-be FastAPI-style leaks):**\n")
            for fp in c["scope_false_positives"]:
                lines.append(f"- `{fp.get('tool_name')}` — {fp.get('scope_reason')}")
        if c["quality_issues"]:
            lines.append("\n**Quality issues:**\n")
            for q in c["quality_issues"]:
                lines.append(f"- `{q.get('tool_name')}` — {q.get('quality_issue')}")
        if audit.get("rubric_recommendation"):
            lines.append(f"\n**Rubric recommendation:** {audit['rubric_recommendation']}")
        if c["verdicts"]:
            lines.append("\n<details><summary>Verdicts surfaced this cycle</summary>\n")
            for v in c["verdicts"]:
                lines.append(
                    f"- **{v.get('tool_name')}** ({v.get('verdict')}, {v.get('category')}) — "
                    f"{(v.get('what') or '')[:120]}"
                )
            lines.append("\n</details>")

    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    return _REPORT_PATH


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RLAIF reinforcement loop for Frontier Scout.")
    parser.add_argument(
        "--cycles", type=int, default=1, help="Max cycles this invocation (stops early when satisfied)."
    )
    parser.add_argument("--cap", type=float, default=_DEFAULT_CAP, help="Hard USD cap for the session.")
    parser.add_argument("--dry-run", action="store_true", help="Plumbing only — no LLM spend (CI-safe).")
    args = parser.parse_args(argv)

    if not args.dry_run:
        # Load real keys (presence only; values never printed). We fill any
        # var that is missing OR empty in the current environment — a parent
        # shell that exports ANTHROPIC_API_KEY="" (common in CLI sessions)
        # would otherwise shadow the real key under load_dotenv(override=False).
        try:
            from dotenv import dotenv_values

            env_local = _REPO_ROOT / ".env.local"
            if env_local.exists():
                filled = 0
                for key, value in dotenv_values(env_local).items():
                    if value and not os.environ.get(key):
                        os.environ[key] = value
                        filled += 1
                print(f"  Loaded {filled} credential(s) from {env_local.name} (values not shown).")
        except Exception:  # noqa: BLE001
            pass
        # A live RLAIF cycle must hit real feeds + LLMs. .env.local ships
        # DRY_RUN=1 for safe demos; the loop explicitly opts into live mode.
        os.environ["DRY_RUN"] = "0"
        try:
            from frontier_scout.providers import resolve_provider

            provider = resolve_provider()
            print(f"  Provider: {provider.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ No usable LLM provider: {exc}", file=sys.stderr)
            return 2

    cycles: list[dict] = []
    satisfied = False
    consecutive_clean = 0

    for n in range(1, args.cycles + 1):
        spend = _session_spend()
        print(f"\n  Session spend so far: ${spend:.4f} / ${args.cap:.2f} cap")
        if spend >= args.cap:
            print(f"  ⛔ Budget cap reached (${spend:.4f} ≥ ${args.cap:.2f}). Stopping before cycle {n}.")
            break

        record = run_cycle(n, dry_run=args.dry_run)
        cycles.append(record)

        if record["clean"]:
            consecutive_clean += 1
        else:
            consecutive_clean = 0

        if consecutive_clean >= 2:
            satisfied = True
            print("\n  ✅ Two consecutive clean cycles — RLAIF loop satisfied.")
            break

    spend = _session_spend()
    report = write_report(cycles, cap=args.cap, spend=spend, satisfied=satisfied)
    print(f"\n  Session spend: ${spend:.4f} / ${args.cap:.2f}")
    print(f"  Report: {report}")

    if cycles and not satisfied and not args.dry_run:
        last = cycles[-1]
        if last["scope_false_positives"] or last["quality_issues"]:
            print(
                "\n  ⚠️  Findings remain. Tighten the rubric/backstop "
                "(scripts/prompts.py, scripts/tools.py, frontier_scout.scout) "
                "and rerun with the same RLAIF_SESSION to continue the loop."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
