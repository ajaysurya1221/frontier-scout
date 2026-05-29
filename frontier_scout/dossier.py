"""Adoption dossiers that connect Scout verdicts, repo fit, and safety gaps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .evaluate import Evaluation, evaluate_url
from .policy import evaluate_policy, load_policy
from .profile import ScoutProfile, build_scout_profile, stack_from_profile
from .scout import personalize_verdicts
from .store import (
    find_latest_verdict,
    home_dir,
    latest_trial_for_tool,
    list_dependency_findings,
    save_evaluation,
    save_permission_manifest,
    save_policy_findings,
)


def build_dossier(
    target: str,
    *,
    repo: Path | None = None,
    reporter: "ProgressReporter | None" = None,
) -> dict[str, Any]:
    """Build and persist a local adoption dossier for a tool or URL.

    v1.3.0 — accepts an optional ``reporter`` (see
    ``frontier_scout.progress``). ``None`` is a no-op.
    """

    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    progress.stage("Gathering local signals", total_stages=3)
    repo_path = repo or Path.cwd()
    profile = build_scout_profile(repo_path)
    verdict = find_latest_verdict(target)
    progress.stage("Evaluating capabilities", total_stages=3)
    evaluation = _evaluation_from_target(target, profile)
    if verdict:
        verdict = personalize_verdicts([verdict], profile.model_dump())[0]
    manifest = evaluation.permission_manifest
    policy = load_policy(repo_path)
    decision = evaluate_policy(evaluation, manifest, policy=policy)
    progress.stage("Compiling brief", total_stages=3)
    tool_id = save_evaluation(evaluation)
    if manifest:
        save_permission_manifest(tool_id, manifest)
    save_policy_findings(tool_id, decision.findings)
    latest_trial = latest_trial_for_tool(evaluation.tool_name)
    dependency_findings = _matching_dependency_findings(target, evaluation.tool_name)

    payload = {
        "tool_name": evaluation.tool_name,
        "source_url": evaluation.source_url,
        "category": evaluation.category,
        "verdict": decision.verdict,
        "policy_summary": decision.summary,
        "repo_profile": _profile_summary(profile),
        "fit": evaluation.fit,
        "risk": evaluation.risk,
        "source_trust": evaluation.source_trust,
        "why_trending": _why_trending(verdict, evaluation),
        "fit_reasons": (verdict or {}).get("fit_reasons") or _fit_reasons(evaluation, profile),
        "permission_manifest": manifest.model_dump() if manifest else None,
        "unknowns": _dedupe(
            list((verdict or {}).get("unknowns") or [])
            + _dossier_unknowns(evaluation, latest_trial)
        ),
        "alternatives": _alternatives(evaluation.category),
        "next_safe_step": _next_safe_step(evaluation, latest_trial),
        "latest_trial": latest_trial,
        "dependency_findings": dependency_findings,
        "receipt_path": str(_dossier_path(evaluation.tool_name)),
    }
    path = _dossier_path(evaluation.tool_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dossier_markdown(payload))
    return payload


def render_dossier_markdown(payload: dict[str, Any]) -> str:
    manifest = payload.get("permission_manifest") or {}
    caps = manifest.get("capabilities") or {}
    lines = [
        f"# Adoption dossier: {payload['tool_name']}",
        "",
        f"Source: {payload['source_url']}",
        f"Verdict: {str(payload['verdict']).upper()}",
        f"Policy: {payload['policy_summary']}",
        f"Fit: {payload['fit']}  Risk: {payload['risk']}  Source trust: {payload['source_trust']}",
        "",
        "## Why it is on the radar",
        "",
        str(payload.get("why_trending") or "Source-backed item surfaced by Scout."),
        "",
        "## Repo fit",
        "",
    ]
    for reason in payload.get("fit_reasons") or []:
        lines.append(f"- {reason}")
    lines.extend(["", "## Permission map", ""])
    for key in sorted(caps):
        lines.append(f"- {key}: {caps[key]}")
    lines.extend(["", "## Unknowns / gaps", ""])
    for gap in payload.get("unknowns") or []:
        lines.append(f"- {gap}")
    lines.extend(["", "## Alternatives / comparables", ""])
    for alt in payload.get("alternatives") or []:
        lines.append(f"- {alt}")
    lines.extend(["", "## Next safe step", "", str(payload.get("next_safe_step") or "Review before adoption.")])
    if payload.get("dependency_findings"):
        lines.extend(["", "## Dependency intelligence", ""])
        for finding in payload["dependency_findings"]:
            lines.append(
                "- "
                f"{finding['package_name']} {finding['from_version']} -> {finding['to_version']} "
                f"({finding['classification']})"
            )
    return "\n".join(lines).rstrip() + "\n"


def _evaluation_from_target(target: str, profile: ScoutProfile) -> Evaluation:
    verdict = find_latest_verdict(target)
    url = target if target.startswith(("http://", "https://")) else None
    if not url and verdict and verdict.get("source_url"):
        url = str(verdict["source_url"])
    if not url and "/" in target:
        url = f"https://github.com/{target}"
    if not url:
        url = f"https://pypi.org/project/{target}/"
    return evaluate_url(url, stack_from_profile(profile), source_text=_source_text(verdict))


def _source_text(verdict: dict[str, Any] | None) -> str | None:
    if not verdict:
        return None
    return " ".join(str(verdict.get(key, "")) for key in ("tool_name", "category", "what", "why_it_matters", "tags"))


def _why_trending(verdict: dict[str, Any] | None, evaluation: Evaluation) -> str:
    if verdict:
        parts = [
            verdict.get("why_this_week"),
            verdict.get("why_it_matters"),
        ]
        return " ".join(str(p) for p in parts if p).strip() or "Scout surfaced this from the latest source-backed scan."
    return (
        f"{evaluation.source_trust.title()}-trust source with category "
        f"{evaluation.category}; use Scout evidence before installation."
    )


def _fit_reasons(evaluation: Evaluation, profile: ScoutProfile) -> list[str]:
    stack = stack_from_profile(profile)
    reasons = []
    blob = " ".join(
        str(v).lower()
        for values in stack.values()
        for v in (values if isinstance(values, list) else [values])
    )
    if evaluation.fit == "high":
        reasons.append("high local stack fit from repo profile")
    if "agent" in blob or "mcp" in blob:
        reasons.append("repo already has agent/MCP-adjacent signals")
    if not reasons:
        reasons.append("no strong local stack match detected yet")
    return reasons


def _dossier_unknowns(evaluation: Evaluation, latest_trial: dict[str, Any] | None) -> list[str]:
    gaps = []
    if not latest_trial:
        gaps.append("no stored trial receipt for this tool")
    if evaluation.permission_manifest and evaluation.permission_manifest.dangerous_flags:
        flags = ", ".join(evaluation.permission_manifest.dangerous_flags)
        gaps.append(f"dangerous capabilities require explicit review: {flags}")
    if evaluation.category in {"dev_tool", "agent_framework"}:
        gaps.append("supported runtime smoke test may still be needed")
    if evaluation.category == "mcp_server":
        gaps.append("capability manifest may be incomplete without server introspection")
    return gaps


def _alternatives(category: str) -> list[str]:
    return {
        "mcp_server": ["Use a read-only MCP server first", "Compare against official MCP reference servers"],
        "agent_framework": ["Compare against LangGraph, Mastra, PydanticAI, or direct SDK code"],
        "model_drop": [
            "Compare against hosted frontier model baseline",
            "Check smaller local variants before self-hosting",
        ],
        "skill": ["Inspect one copied skill manually before installing a bundle"],
    }.get(category, ["Manual review", "Wait for stronger maintainer and adoption evidence"])


def _next_safe_step(evaluation: Evaluation, latest_trial: dict[str, Any] | None) -> str:
    if latest_trial:
        return "Review the stored trial receipt and decide whether to approve a narrow production trial."
    if evaluation.category == "mcp_server":
        return (
            f"Run `frontier-scout trial {evaluation.tool_name} "
            f"--url {evaluation.source_url} --dry-run` before granting tools."
        )
    if evaluation.category == "model_drop":
        return "Run a small benchmark fixture before allocating GPU or integration time."
    return (
        f"Run `frontier-scout trial {evaluation.tool_name} "
        f"--url {evaluation.source_url} --dry-run` before installing in a real repo."
    )


def _profile_summary(profile: ScoutProfile) -> dict[str, Any]:
    return {
        "repo": profile.repo,
        "languages": profile.languages,
        "frameworks": profile.frameworks,
        "agent_configs": profile.agent_configs,
        "risk_flags": profile.risk_flags,
    }


def _dossier_path(tool_name: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", tool_name).strip("-").lower() or "tool"
    return home_dir() / "reports" / "dossiers" / f"{slug}.md"


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _matching_dependency_findings(target: str, tool_name: str) -> list[dict[str, Any]]:
    needle = target.lower().strip()
    tool_needle = tool_name.lower().strip()
    matches = []
    for finding in list_dependency_findings():
        package = str(finding.get("package_name", "")).lower()
        if package and (package in needle or needle in package or package in tool_needle):
            matches.append(finding.get("payload") or finding)
    return matches[:5]
