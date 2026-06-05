"""Orchestration for the sanctioned-pack flow: candidates -> safety -> sanction -> export.

Thin, store-backed, deterministic, offline-capable. The CLI (``cli.py``) is a formatting shell
over these functions. This is the core MVP user journey of the pivot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import store
from .exporters import export_claude_config
from .packs import (
    REMOVE_OVERRIDES,
    PackCandidate,
    apply_pack_overrides,
    default_packs,
    demo_mcp_servers,
    rank_candidates_for_repo,
)
from .profile import build_scout_profile
from .proof_variants import proof_variants
from .safety_summary import build_safety_summary, is_high_risk
from .telemetry import record_event

SUPPORTED_CLIENTS = ("claude-code", "copilot", "cursor")


def _client_allows(candidate: PackCandidate, client: str) -> bool:
    """A candidate is offered for a client unless it explicitly restricts its scope."""

    scope = (candidate.server_meta or {}).get("client_scope")
    return not scope or client in scope


def _candidate_from_row(row: dict[str, Any]) -> PackCandidate:
    return PackCandidate(
        pack_slug=row.get("pack_slug", "mcp"),
        tool_name=row["tool_name"],
        state=row.get("state", "candidate"),
        category=row.get("category"),
        description=row.get("description", "") or "",
        tags=row.get("tags") or [],
        server_meta=row.get("server_meta") or {},
        repo_fit=row.get("repo_fit"),
        freshness_score=float(row.get("freshness_score") or 0.0),
        consensus_score=float(row.get("consensus_score") or 0.0),
        evidence=row.get("evidence") or [],
    )


def get_candidates(
    repo: str | Path = ".",
    *,
    client: str = "claude-code",
    discover: bool = False,
    pack_slug: str = "mcp",
    persist: bool = True,
) -> list[PackCandidate]:
    """Build the repo-ranked candidate list for a pack + client.

    Keyless by default: starts from the curated offline demo pack (real, popular MCP
    servers with runnable server_meta). ``discover=True`` additionally fetches live
    MCP-registry servers (network) and merges the runnable ones.
    """

    from .packs import _mcp_registry_candidates

    profile = build_scout_profile(Path(repo))
    base = list(demo_mcp_servers())
    if discover:
        pack = default_packs().get(pack_slug)
        if pack is not None and pack.discovery.mcp_registry_url:
            seen = {c.tool_name for c in base}
            for candidate in _mcp_registry_candidates(pack):
                if candidate.tool_name not in seen and (candidate.server_meta or {}).get("transport") != "unknown":
                    base.append(candidate)
                    seen.add(candidate.tool_name)
    ranked = rank_candidates_for_repo(base, profile)
    ranked = apply_pack_overrides(ranked, store.list_pack_overrides(pack_slug))
    ranked = [c for c in ranked if _client_allows(c, client)]
    if persist:
        for candidate in ranked:
            store.save_pack_candidate(candidate)
        record_event("candidates_viewed", count=len(ranked), client=client, pack=pack_slug)
    return ranked


def _find_candidate(server_name: str, *, repo: str | Path, client: str, pack_slug: str) -> PackCandidate | None:
    for row in store.list_pack_candidates(pack_slug):
        if row["tool_name"] == server_name:
            return _candidate_from_row(row)
    for candidate in get_candidates(repo, client=client, pack_slug=pack_slug, persist=False):
        if candidate.tool_name == server_name:
            return candidate
    return None


def sanction_server(
    server_name: str,
    *,
    repo: str | Path = ".",
    client: str = "claude-code",
    pack_slug: str = "mcp",
    approver: str | None = None,
    reason: str | None = None,
    acknowledge_risk: bool = False,
) -> dict[str, Any]:
    """Sanction a server, gating high-risk ones behind an explicit acknowledgement."""

    candidate = _find_candidate(server_name, repo=repo, client=client, pack_slug=pack_slug)
    if candidate is None:
        return {"ok": False, "error": f"unknown server: {server_name}"}
    summary = build_safety_summary(candidate)
    if is_high_risk(summary) and not acknowledge_risk:
        record_event("sanction_blocked", server=server_name, client=client)
        return {
            "ok": False,
            "blocked": True,
            "reason": "high-risk",
            "summary": summary,
            "message": (
                f"{server_name} has high-risk capabilities "
                f"({', '.join(summary['dangerous_flags'])}); review the static safety "
                f"summary and re-run with --acknowledge-risk to sanction it."
            ),
        }
    store.save_pack_candidate(candidate.model_copy(update={"state": "sanctioned"}))
    store.save_adoption_decision(
        server_name,
        "sanctioned",
        pack_slug=pack_slug,
        client=client,
        approver_label=approver,
        rationale=reason,
        payload={"server_meta": candidate.server_meta, "verdict": summary["verdict"]},
    )
    record_event("sanctioned", server=server_name, client=client, verdict=summary["verdict"])
    return {"ok": True, "server": server_name, "verdict": summary["verdict"], "summary": summary}


def unsanction_server(
    server_name: str,
    *,
    client: str = "claude-code",
    pack_slug: str = "mcp",
    reason: str | None = None,
) -> dict[str, Any]:
    """Unsanction a server: exclude it from exports and record the reversal."""

    store.save_pack_override(pack_slug, server_name, "exclude", reason=reason or "unsanctioned")
    store.save_adoption_decision(server_name, "unsanctioned", pack_slug=pack_slug, client=client, rationale=reason)
    for row in store.list_pack_candidates(pack_slug):
        if row["tool_name"] == server_name and row.get("state") == "sanctioned":
            store.save_pack_candidate(_candidate_from_row({**row, "state": "candidate"}))
    record_event("unsanctioned", server=server_name, client=client)
    return {"ok": True, "server": server_name}


def export_config(*, client: str = "claude-code", pack_slug: str = "mcp", target_dir: str | Path) -> dict[str, Any]:
    """Export the sanctioned set into the client's control-plane config."""

    sanctioned = [
        _candidate_from_row(row) for row in store.list_pack_candidates(pack_slug) if row.get("state") == "sanctioned"
    ]
    denied = [
        override["tool_identifier"]
        for override in store.list_pack_overrides(pack_slug)
        if override.get("override") in REMOVE_OVERRIDES
    ]
    # All MVP clients (claude-code/copilot/cursor) consume the same mcpServers /
    # managed allow-deny shapes, so one exporter covers them.
    paths = export_claude_config(sanctioned, denied=denied, target_dir=target_dir)
    record_event("exported", client=client, count=len(sanctioned))
    return {
        "ok": True,
        "client": client,
        "sanctioned_count": len(sanctioned),
        "denied_count": len(denied),
        "paths": paths,
    }


def server_proof(
    server_name: str, *, repo: str | Path = ".", client: str = "claude-code", pack_slug: str = "mcp"
) -> dict[str, Any]:
    """Render the three A/B/C proof variants for a server (validation step 2)."""

    candidate = _find_candidate(server_name, repo=repo, client=client, pack_slug=pack_slug)
    if candidate is None:
        return {"ok": False, "error": f"unknown server: {server_name}"}
    summary = build_safety_summary(candidate)
    record_event("safety_viewed", server=server_name, client=client)
    return {"ok": True, "server": server_name, "variants": proof_variants(summary)}
