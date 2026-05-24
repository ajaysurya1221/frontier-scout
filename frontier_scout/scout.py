"""CLI-facing scan helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .report import SAMPLE_FUNNEL, SAMPLE_VERDICTS
from .store import save_scan


def detect_stack(repo: Path) -> dict[str, Any]:
    """Best-effort stack profile from common project files.

    This is deliberately conservative. It records signals for ranking prompts
    without uploading local source code.
    """
    repo = repo.resolve()
    files = {p.name for p in repo.iterdir()} if repo.exists() and repo.is_dir() else set()
    signals: dict[str, Any] = {
        "repo": str(repo),
        "languages": [],
        "frameworks": [],
        "package_managers": [],
        "agent_configs": [],
    }
    if "package.json" in files:
        signals["languages"].append("javascript/typescript")
        signals["package_managers"].append("npm")
        _read_package_json(repo / "package.json", signals)
    if "pyproject.toml" in files or "requirements.txt" in files:
        signals["languages"].append("python")
        signals["package_managers"].append("pip")
    if "Cargo.toml" in files:
        signals["languages"].append("rust")
        signals["package_managers"].append("cargo")
    if "go.mod" in files:
        signals["languages"].append("go")
        signals["package_managers"].append("go")
    if "Dockerfile" in files or "docker-compose.yml" in files:
        signals["frameworks"].append("docker")
    for candidate in (
        ".mcp.json",
        "mcp.json",
        "CLAUDE.md",
        "AGENTS.md",
        ".cursor",
        ".codex",
    ):
        if (repo / candidate).exists():
            signals["agent_configs"].append(candidate)
    return signals


def run_scan(
    *,
    repo: Path | None = None,
    dry_run: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    repo = repo or Path.cwd()
    stack = detect_stack(repo)
    if dry_run:
        payload = {
            "date": SAMPLE_FUNNEL.get("date", "2026-05-21"),
            "stack": stack,
            "scanned": SAMPLE_FUNNEL["items_scanned"],
            "candidates": SAMPLE_FUNNEL["candidates"],
            "cost_usd": 0.0,
            "duration_s": 0.0,
            "judge_rating": "demo",
            "judge_summary": "Dry-run scan using seeded demo verdicts.",
            "verdicts": SAMPLE_VERDICTS,
        }
    else:
        payload = _run_live_scan(stack)
        payload["stack"] = stack
    if persist:
        save_scan(payload, repo=str(repo.resolve()))
    return payload


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


def _read_package_json(path: Path, signals: dict[str, Any]) -> None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    deps = {
        **(data.get("dependencies") or {}),
        **(data.get("devDependencies") or {}),
    }
    for name in deps:
        low = name.lower()
        if low in {"next", "react", "vue", "svelte", "express", "fastify"}:
            signals["frameworks"].append(low)
        if low in {"langchain", "llamaindex", "ai", "@modelcontextprotocol/sdk"}:
            signals["frameworks"].append(low)

