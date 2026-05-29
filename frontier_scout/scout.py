"""CLI-facing scan helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .packs import default_packs
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
    pack: str | None = None,
    discover: bool = False,
    reporter: "ProgressReporter | None" = None,
) -> dict[str, Any]:
    """Run an AI-tool scout against the given repo.

    v1.3.0 — accepts an optional ``reporter`` that receives staged
    progress events ("Detecting stack", "Querying judge",
    "Personalising verdicts"). ``None`` is the default and a true
    no-op; every existing caller is unaffected.
    """

    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    total = 3 if dry_run else 4
    progress.stage("Detecting stack", total_stages=total)
    repo = repo or Path.cwd()
    stack = detect_stack(repo)
    profile = build_scout_profile(repo)
    if dry_run:
        progress.stage("Loading seeded verdicts", total_stages=total)
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
            "pack": pack,
            "discover": discover,
            "verdicts": personalize_verdicts(_filter_by_pack(SAMPLE_VERDICTS, pack), profile.model_dump()),
        }
        progress.stage("Personalising verdicts", total_stages=total)
        # personalize_verdicts already ran in the dict literal above;
        # the stage event marks "we're producing the final result".
    else:
        progress.stage("Querying judge", total_stages=total)
        payload = _run_live_scan(stack)
        payload["stack"] = stack
        payload["profile"] = profile.model_dump()
        payload["pack"] = pack
        payload["discover"] = discover
        progress.stage("Personalising verdicts", total_stages=total)
        payload["verdicts"] = personalize_verdicts(list(payload.get("verdicts") or []), profile.model_dump())
    if persist:
        progress.stage("Saving scan", total_stages=total)
        save_scan(payload, repo=str(repo.resolve()))
    progress.log(
        f"Scout complete: {len(payload.get('verdicts') or [])} verdict(s)",
        tone="ok",
    )
    return payload


def personalize_verdicts(verdicts: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Annotate verdicts with local fit reasons, honest unknowns, and a
    v1.2.1 concern taxonomy ("burns tokens", "abandoned", "rip-off"...).

    Every concern carries a slug, a human label, a severity
    (``high|medium|low``), and one line of plain-language evidence so
    the Scout-tab detail panel never has to ask "why?". See the
    Stream-K plan + tests/test_verdict_concerns.py for the rule
    contract; LLM-generated concerns are explicitly v1.2.2.
    """

    out = []
    for verdict in verdicts:
        item = dict(verdict)
        fit, reasons = _personal_fit(item, profile)
        if fit:
            item["fit"] = fit
        item["fit_reasons"] = reasons
        item["unknowns"] = _unknowns(item)
        item["next_safe_step"] = _next_safe_step(item)
        item["concerns"] = _concerns(item)
        out.append(item)
    return out


#: Source-URL prefixes that strongly imply lock-in to one vendor.
_VENDOR_LOCK_IN_DOMAINS = (
    "anthropic.com",
    "openai.com",
    "platform.openai.com",
    "google.com",
    "cloud.google.com",
    "aws.amazon.com",
    "microsoft.com",
    "azure.com",
)


def _concerns(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic concern rules.

    Each concern is ``{"slug", "label", "severity", "evidence"}``. The
    rules are intentionally conservative — false-positive "rip-off"
    accusations would burn user trust faster than a missed concern.
    """

    concerns: list[dict[str, Any]] = []
    category = str(verdict.get("category") or "").lower()
    fit = str(verdict.get("fit") or "").lower()
    fit_reasons = verdict.get("fit_reasons") or []
    source_url = str(verdict.get("source_url") or "").lower()
    what = str(verdict.get("what") or "")
    manifest = verdict.get("permission_manifest") or {}
    dangerous = list(manifest.get("dangerous_flags") or [])
    cost = verdict.get("cost_per_call_usd")
    age = verdict.get("last_release_age_days")
    lock_in = str(verdict.get("lock_in_risk") or "none").lower()

    # weak_fit — the personalization stage couldn't connect the tool to
    # anything in the local stack.
    if fit == "low" or fit_reasons == ["no strong local stack match detected"]:
        concerns.append(
            {
                "slug": "weak_fit",
                "label": "weak fit for your repo",
                "severity": "low",
                "evidence": (
                    "no strong local stack match detected — adopt only if "
                    "you have a specific reason this tool maps to your work"
                ),
            }
        )

    # token_burn — large models or any tool with a per-call cost hint
    # over $0.05.
    if category == "model_drop":
        concerns.append(
            {
                "slug": "token_burn",
                "label": "burns tokens",
                "severity": "medium",
                "evidence": (
                    "model drops bill per-token at inference time and pile "
                    "up fast under unattended use"
                ),
            }
        )
    elif isinstance(cost, (int, float)) and cost > 0.05:
        concerns.append(
            {
                "slug": "token_burn",
                "label": "burns tokens",
                "severity": "medium",
                "evidence": (
                    f"estimated cost ${cost:.3f}/call — multiply by your "
                    "actual call rate before adoption"
                ),
            }
        )

    # abandoned — > 9 months since last release.
    if isinstance(age, (int, float)) and age > 270:
        concerns.append(
            {
                "slug": "abandoned",
                "label": "looks abandoned",
                "severity": "high",
                "evidence": (
                    f"last release was {int(age)} days ago; no public "
                    "evidence of active maintenance"
                ),
            }
        )

    # security_surface — any dangerous capability flag on the manifest.
    risky = set(dangerous) & {"write", "shell", "credential", "unknown"}
    if risky:
        concerns.append(
            {
                "slug": "security_surface",
                "label": "security surface",
                "severity": "high",
                "evidence": (
                    f"permission manifest carries: {', '.join(sorted(risky))} "
                    "— sandbox before adoption"
                ),
            }
        )

    # vendor_lock_in — explicit risk OR source on a major vendor's domain.
    if lock_in in {"medium", "high"}:
        concerns.append(
            {
                "slug": "vendor_lock_in",
                "label": "vendor lock-in",
                "severity": "medium" if lock_in == "medium" else "high",
                "evidence": (
                    "switching away later will mean rewriting against a "
                    "different API surface"
                ),
            }
        )
    elif any(domain in source_url for domain in _VENDOR_LOCK_IN_DOMAINS):
        # We don't add this for category=skill/mcp_server because the
        # spec there is open — only for closed vendor SDKs.
        if category in {"vendor_tool", "model_drop", "dev_tool"}:
            concerns.append(
                {
                    "slug": "vendor_lock_in",
                    "label": "vendor lock-in",
                    "severity": "low",
                    "evidence": (
                        f"hosted on a major vendor's surface ({source_url})"
                    ),
                }
            )

    # marketing_only — short, vague description with no GitHub source.
    if (
        len(what.strip()) < 40
        and "github.com" not in source_url
        and "huggingface.co" not in source_url
    ):
        concerns.append(
            {
                "slug": "marketing_only",
                "label": "marketing-only",
                "severity": "medium",
                "evidence": (
                    "description is short and no public code repo is "
                    "linked — could be a landing page, not a tool"
                ),
            }
        )

    # unproven — agent frameworks / MCP servers that we have no lab
    # receipt for yet. We don't crash on a missing helper here.
    if category in {"agent_framework", "mcp_server"}:
        try:
            from frontier_scout.store import latest_trial_for_tool

            receipt = latest_trial_for_tool(str(verdict.get("tool_name", "")))
        except Exception:  # noqa: BLE001 — defensive
            receipt = None
        if not receipt:
            concerns.append(
                {
                    "slug": "unproven",
                    "label": "unproven",
                    "severity": "low",
                    "evidence": (
                        "no local lab/trial receipt on file yet — your "
                        "first run is the test"
                    ),
                }
            )

    return concerns


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


def _filter_by_pack(verdicts: list[dict[str, Any]], pack: str | None) -> list[dict[str, Any]]:
    if not pack:
        return verdicts
    pack_def = default_packs().get(pack)
    if not pack_def:
        return verdicts
    needles = {repo.lower() for repo in pack_def.seed_repos}
    filtered = [
        verdict
        for verdict in verdicts
        if str(verdict.get("tool_name", "")).lower() in needles
        or any(str(verdict.get("source_url", "")).lower().endswith(repo.lower()) for repo in needles)
    ]
    return filtered or verdicts


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
