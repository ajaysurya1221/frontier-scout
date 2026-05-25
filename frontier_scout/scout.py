"""CLI-facing scan helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .profile import build_scout_profile, stack_from_profile
from .report import SAMPLE_FUNNEL, SAMPLE_VERDICTS
from .store import save_scan


def detect_stack(repo: Path) -> dict[str, Any]:
    """Best-effort stack profile from common project files.

    This is deliberately conservative. It records signals for ranking prompts
    without uploading local source code.
    """
    return stack_from_profile(build_scout_profile(repo))


def run_scan(
    *,
    repo: Path | None = None,
    dry_run: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    repo = repo or Path.cwd()
    stack = detect_stack(repo)
    profile = build_scout_profile(repo)
    if dry_run:
        payload = {
            "date": SAMPLE_FUNNEL.get("date", "2026-05-21"),
            "stack": stack,
            "profile": profile.model_dump(),
            "scanned": SAMPLE_FUNNEL["items_scanned"],
            "candidates": SAMPLE_FUNNEL["candidates"],
            "cost_usd": 0.0,
            "duration_s": 0.0,
            "judge_rating": "demo",
            "judge_summary": "Dry-run scan using seeded demo verdicts.",
            "verdicts": personalize_verdicts(SAMPLE_VERDICTS, profile.model_dump()),
        }
    else:
        payload = _run_live_scan(stack)
        payload["stack"] = stack
        payload["profile"] = profile.model_dump()
        payload["verdicts"] = personalize_verdicts(list(payload.get("verdicts") or []), profile.model_dump())
    if persist:
        save_scan(payload, repo=str(repo.resolve()))
    return payload


def personalize_verdicts(verdicts: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Annotate verdicts with local fit reasons and honest unknowns."""

    out = []
    for verdict in verdicts:
        item = dict(verdict)
        fit, reasons = _personal_fit(item, profile)
        if fit:
            item["fit"] = fit
        item["fit_reasons"] = reasons
        item["unknowns"] = _unknowns(item)
        item["next_safe_step"] = _next_safe_step(item)
        out.append(item)
    return out


def _personal_fit(verdict: dict[str, Any], profile: dict[str, Any]) -> tuple[str | None, list[str]]:
    blob = " ".join(
        str(value).lower()
        for key in ("languages", "frameworks", "package_managers", "agent_configs", "ai_tooling", "containers", "ci")
        for value in profile.get(key, [])
    )
    text = " ".join(
        str(verdict.get(key, "")).lower()
        for key in ("tool_name", "category", "what", "why_it_matters", "tags")
    )
    reasons: list[str] = []
    score = 0
    if "python" in blob and any(x in text for x in ("python", "browser-use", "pypi", "langgraph")):
        score += 2
        reasons.append("matches Python stack")
    if "javascript/typescript" in blob and any(x in text for x in ("typescript", "javascript", "npm", "mcp", "skill")):
        score += 2
        reasons.append("matches JS/TS tooling")
    if any(x in blob for x in ("mcp", ".mcp.json", "@modelcontextprotocol/sdk")) and "mcp" in text:
        score += 3
        reasons.append("matches existing MCP/agent configuration")
    has_agent_config = any(x in blob for x in ("claude", "codex", "cursor", "agents.md"))
    is_agent_tool = any(x in text for x in ("skill", "agent", "mcp"))
    if has_agent_config and is_agent_tool:
        score += 2
        reasons.append("matches local agent workflow")
    if "docker" in blob and any(x in text for x in ("sandbox", "browser", "agent", "server")):
        score += 1
        reasons.append("Docker available for isolated trials")
    if not reasons:
        reasons.append("no strong local stack match detected")
    if score >= 4:
        return "high", reasons
    if score >= 2:
        return "medium", reasons
    if verdict.get("fit") == "high":
        return "medium", reasons
    return None, reasons


def _unknowns(verdict: dict[str, Any]) -> list[str]:
    unknowns: list[str] = []
    if not verdict.get("source_url"):
        unknowns.append("source URL missing")
    if verdict.get("verdict") in {"adopt", "trial"}:
        unknowns.append("no local sandbox receipt attached to this scout item")
    if verdict.get("category") in {"mcp_server", "agent_framework"}:
        unknowns.append("runtime permission surface needs explicit review")
    if verdict.get("category") == "model_drop":
        unknowns.append("local hardware and independent eval fit not proven")
    return unknowns


def _next_safe_step(verdict: dict[str, Any]) -> str:
    source = verdict.get("source_url") or verdict.get("tool_name") or "<tool>"
    if verdict.get("verdict") == "hold":
        return "Do not install; revisit only if independent evidence changes."
    if verdict.get("category") in {"mcp_server", "agent_framework", "skill"}:
        return f"Run `frontier-scout evaluate {source}` then create a dry-run receipt."
    if verdict.get("category") == "model_drop":
        return "Benchmark against a small local fixture before spending integration time."
    return str(verdict.get("next_action") or "Review the source evidence before trial.")


def _run_live_scan(stack_profile: dict[str, Any]) -> dict[str, Any]:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    os.environ.setdefault("FRONTIER_SCOUT_HOME", str(Path("~/.frontier-scout").expanduser()))
    from scout import run_scan as legacy_run_scan  # type: ignore

    result = legacy_run_scan(stack_profile=stack_profile, dry_run=False)
    return {
        "scanned": result.scanned,
        "candidates": result.candidates,
        "dedup_drops": result.dedup_drops,
        "seen_drops": result.seen_drops,
        "cost_usd": result.cost_usd,
        "duration_s": result.duration_s,
        "judge_summary": result.judge_summary,
        "judge_rating": result.judge_rating,
        "judge_used_fallback": result.judge_used_fallback,
        "verdicts": result.verdicts,
    }

