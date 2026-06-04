"""Living Scout Pack definitions and deterministic lifecycle rules."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

PackState = Literal["candidate", "watched", "core", "retired", "sanctioned"]
PackCandidateState = PackState


class PackDiscovery(BaseModel):
    """Discovery inputs for a living Scout Pack."""

    github_queries: list[str] = Field(default_factory=list)
    github_topics: list[str] = Field(default_factory=list)
    hn_keywords: list[str] = Field(default_factory=list)
    rss_urls: list[str] = Field(default_factory=list)
    package_namespaces: list[str] = Field(default_factory=list)
    mcp_registry_url: str | None = None
    hf_filters: list[str] = Field(default_factory=list)


class ScoutPack(BaseModel):
    """A non-exclusive, living tag for related AI adoption tools."""

    slug: str
    display_name: str
    description: str
    seed_repos: list[str] = Field(default_factory=list)
    trusted_topics: list[str] = Field(default_factory=list)
    discovery: PackDiscovery = Field(default_factory=PackDiscovery)
    last_verified_at: str = "2026-05-26"


class CandidateEvidence(BaseModel):
    """One source-family signal for a pack candidate."""

    source_family: str
    source: str
    score: float = Field(ge=0, le=1)
    days_ago: int = Field(default=0, ge=0)


class PackCandidate(BaseModel):
    """A candidate tool's lifecycle state inside one pack."""

    pack_slug: str
    tool_name: str
    state: PackState = "candidate"
    evidence: list[CandidateEvidence] = Field(default_factory=list)
    freshness_score: float = 0.0
    consensus_score: float = 0.0
    independent_source_families: int = 0
    verdict_appearances: int = 0
    weekly_scan_span: int = 0
    has_high_risk: bool = False
    days_since_release: int | None = None
    issue_response_p90_days: int | None = None
    star_growth_z: float | None = None
    # v1.9 (pivot): enrichment consumed by the repo-aware ranker + config exporter.
    category: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    server_meta: dict[str, Any] = Field(default_factory=dict)
    # repo-specific fit tier ("high"/"medium"/"low"), set by rank_candidates_for_repo.
    repo_fit: str | None = None


@dataclass(frozen=True)
class SourceHealth:
    """Runtime health of one discovery source."""

    source_id: str
    zero_item_runs: int = 0
    source_state: Literal["active", "stale"] = "active"


def default_packs() -> dict[str, ScoutPack]:
    """Return built-in pack seed definitions.

    These seeds bootstrap the radar. They are deliberately not the permanent
    source of truth: discovery can add, promote, demote, or retire candidates.
    """

    packs = [
        ScoutPack(
            slug="ai-devtools",
            display_name="AI Developer Tools",
            description="Coding assistants, repo agents, and AI-native developer workflows.",
            seed_repos=[
                "Aider-AI/aider",
                "continuedev/continue",
                "OpenHands/OpenHands",
                "stackblitz-labs/bolt.diy",
            ],
            trusted_topics=["ai-coding", "developer-tools", "coding-agent"],
            discovery=PackDiscovery(
                github_queries=["topic:ai-coding stars:>500", "topic:developer-tools llm"],
                hn_keywords=["ai coding", "coding agent", "developer tool"],
                rss_urls=["https://github.blog/changelog/feed/"],
            ),
        ),
        ScoutPack(
            slug="mcp",
            display_name="Model Context Protocol",
            description="MCP servers, SDKs, registries, and capability surfaces.",
            seed_repos=[
                "modelcontextprotocol/servers",
                "modelcontextprotocol/python-sdk",
                "modelcontextprotocol/typescript-sdk",
            ],
            trusted_topics=["mcp", "model-context-protocol"],
            discovery=PackDiscovery(
                github_queries=["topic:mcp stars:>100", '"model context protocol"'],
                github_topics=["mcp", "model-context-protocol"],
                hn_keywords=["mcp", "model context protocol"],
                package_namespaces=["@modelcontextprotocol"],
                mcp_registry_url="https://registry.modelcontextprotocol.io/v0/servers",
            ),
        ),
        ScoutPack(
            slug="agent-frameworks",
            display_name="Agent Frameworks",
            description="Typed and durable agent runtime/framework choices.",
            seed_repos=[
                "langchain-ai/langgraph",
                "openai/openai-agents-python",
                "pydantic/pydantic-ai",
                "mastra-ai/mastra",
                "crewAIInc/crewAI",
                "microsoft/semantic-kernel",
            ],
            trusted_topics=["agents", "agent-framework"],
            discovery=PackDiscovery(
                github_queries=["topic:ai-agents framework", "topic:agent-framework stars:>500"],
                hn_keywords=["agent framework", "multi-agent", "ai agents"],
            ),
        ),
        ScoutPack(
            slug="local-ai",
            display_name="Local AI",
            description="Local model runtimes, inference engines, and self-hosted AI UX.",
            seed_repos=[
                "ollama/ollama",
                "ggerganov/llama.cpp",
                "vllm-project/vllm",
                "open-webui/open-webui",
            ],
            trusted_topics=["llm", "local-ai", "inference"],
            discovery=PackDiscovery(
                github_queries=["topic:local-ai stars:>500", "topic:llm-inference"],
                hn_keywords=["local llm", "ollama", "vllm"],
                hf_filters=["text-generation", "inference"],
            ),
        ),
        ScoutPack(
            slug="rag-memory",
            display_name="RAG and Memory",
            description="RAG frameworks, vector stores, graph memory, and retrieval systems.",
            seed_repos=[
                "run-llama/llama_index",
                "microsoft/graphrag",
                "infiniflow/ragflow",
                "qdrant/qdrant",
                "chroma-core/chroma",
                "getzep/graphiti",
            ],
            trusted_topics=["rag", "vector-search", "knowledge-graph"],
            discovery=PackDiscovery(
                github_queries=["topic:rag stars:>500", "topic:vector-search ai"],
                hn_keywords=["rag", "vector database", "graphrag"],
            ),
        ),
        ScoutPack(
            slug="workflow-builders",
            display_name="Workflow Builders",
            description="AI workflow builders and self-hosted app automation platforms.",
            seed_repos=["langgenius/dify", "langflow-ai/langflow", "FlowiseAI/Flowise"],
            trusted_topics=["workflow", "low-code", "ai-workflow"],
            discovery=PackDiscovery(
                github_queries=["topic:ai-workflow stars:>500", "topic:low-code-ai"],
                hn_keywords=["ai workflow", "dify", "langflow"],
            ),
        ),
        ScoutPack(
            slug="inference-gateway",
            display_name="Inference Gateway",
            description="Provider gateways, model routing, cost controls, and serving layers.",
            seed_repos=["BerriAI/litellm", "LMCache/LMCache", "vllm-project/vllm"],
            trusted_topics=["model-gateway", "llmops", "inference"],
            discovery=PackDiscovery(
                github_queries=["topic:llmops gateway", "topic:model-gateway"],
                hn_keywords=["ai gateway", "llm gateway", "model routing"],
            ),
        ),
    ]
    return {pack.slug: pack for pack in packs}


def apply_lifecycle_rules(candidate: PackCandidate) -> PackCandidate:
    """Apply deterministic promotion/demotion rules to a candidate."""

    consensus, freshness, families = _score_evidence(candidate.evidence)
    state: PackState = candidate.state
    if state == "candidate" and consensus >= 0.6 and families >= 2 and freshness >= 0.5:
        state = "watched"
    elif (
        state == "watched"
        and candidate.verdict_appearances >= 3
        and candidate.weekly_scan_span >= 4
        and not candidate.has_high_risk
    ):
        state = "core"
    elif (
        state == "core"
        and (candidate.days_since_release or 0) >= 180
        and (candidate.issue_response_p90_days or 0) >= 30
        and (candidate.star_growth_z or 0) < -1
    ):
        state = "retired"
    return candidate.model_copy(
        update={
            "state": state,
            "consensus_score": consensus,
            "freshness_score": freshness,
            "independent_source_families": families,
        }
    )


def update_source_health(source_id: str, item_count: int, *, previous_zero_runs: int = 0) -> SourceHealth:
    """Mark sources stale after two consecutive zero-item runs."""

    zero_runs = previous_zero_runs + 1 if item_count == 0 else 0
    return SourceHealth(
        source_id=source_id,
        zero_item_runs=zero_runs,
        source_state="stale" if zero_runs >= 2 else "active",
    )


def _score_evidence(evidence: list[CandidateEvidence]) -> tuple[float, float, int]:
    by_family: dict[str, float] = {}
    freshness_values: list[float] = []
    for item in evidence:
        consensus_decay = 0.5 ** (item.days_ago / 30)
        freshness_decay = 0.5 ** (item.days_ago / 14)
        weighted_score = min(1.0, item.score * consensus_decay)
        by_family[item.source_family] = max(by_family.get(item.source_family, 0.0), weighted_score)
        freshness_values.append(min(1.0, item.score * freshness_decay))
    consensus = min(1.0, sum(by_family.values()))
    freshness = max(freshness_values) if freshness_values else 0.0
    if math.isclose(consensus, 1.0, abs_tol=1e-9):
        consensus = 1.0
    return round(consensus, 4), round(freshness, 4), len(by_family)


def pack_summary_rows() -> list[dict[str, object]]:
    """Compact rows for CLI rendering."""

    rows: list[dict[str, object]] = []
    for pack in default_packs().values():
        rows.append(
            {
                "slug": pack.slug,
                "display_name": pack.display_name,
                "seed_count": len(pack.seed_repos),
                "source_count": len(pack.discovery.github_queries)
                + len(pack.discovery.hn_keywords)
                + len(pack.discovery.rss_urls)
                + (1 if pack.discovery.mcp_registry_url else 0),
            }
        )
    return rows


def candidate_rows_for_pack(
    pack: ScoutPack, *, discover: bool = False, profile: object | None = None
) -> list[PackCandidate]:
    """Return seed and optional live-discovered candidates for a pack.

    When ``profile`` (a ScoutProfile) is given, candidates are ranked by repo fit
    via :func:`rank_candidates_for_repo`; without it the legacy order is preserved.
    """

    candidates = [
        PackCandidate(
            pack_slug=pack.slug,
            tool_name=repo,
            state="core",
            freshness_score=1.0,
            consensus_score=1.0,
            independent_source_families=1,
            evidence=[CandidateEvidence(source_family="github_releases", source="seed", score=1.0)],
        )
        for repo in pack.seed_repos
    ]
    if discover and pack.discovery.mcp_registry_url:
        candidates.extend(_mcp_registry_candidates(pack))
    if profile is not None:
        candidates = rank_candidates_for_repo(candidates, profile)
    return candidates


def pack_candidate_to_fit_input(candidate: PackCandidate, stack: dict) -> tuple[str, str, dict]:
    """Adapt a PackCandidate into the ``(category, text, stack)`` shape evaluate._fit wants.

    MCP-registry candidates default to ``mcp_server``; ``text`` combines name +
    description + tags so the fit heuristic has signal to match against the repo stack.
    """

    category = candidate.category or "mcp_server"
    text = " ".join(part for part in (candidate.tool_name, candidate.description, " ".join(candidate.tags)) if part)
    return category, text, stack


_FIT_RANK = {"high": 2, "medium": 1, "low": 0}


def rank_candidates_for_repo(candidates: list[PackCandidate], profile: object) -> list[PackCandidate]:
    """Rank candidates by deterministic repo fit (highest first).

    Reuses the public :func:`frontier_scout.evaluate.repo_fit` scorer and the repo
    stack from ``stack_from_profile`` — both offline/deterministic (no LLM, no
    network). Stable: ties keep input order.
    """

    from .evaluate import repo_fit as _repo_fit
    from .profile import stack_from_profile

    stack = stack_from_profile(profile) if profile is not None else {}
    scored: list[PackCandidate] = []
    for candidate in candidates:
        category, text, _ = pack_candidate_to_fit_input(candidate, stack)
        fit = _repo_fit(category, text, stack) if stack else "low"
        scored.append(candidate.model_copy(update={"repo_fit": fit}))
    scored.sort(
        key=lambda c: (
            _FIT_RANK.get(c.repo_fit or "low", 0),
            c.consensus_score,
            c.freshness_score,
        ),
        reverse=True,
    )
    return scored


_OVERRIDE_RANK = {"exclude": 3, "suppress": 3, "retire": 3, "pin": 2, "include": 1}


def apply_pack_overrides(candidates: list[PackCandidate], overrides: list[dict]) -> list[PackCandidate]:
    """Filter/reorder candidates by stored pack overrides.

    Precedence per tool: exclude > pin > include (exclude/suppress/retire all
    remove). Pinned candidates move to the front, preserving relative order.
    Overrides are read via ``store.list_pack_overrides`` and passed in here so
    this stays a pure, store-free transform.
    """

    best_rank: dict[str, int] = {}
    effective: dict[str, str] = {}
    for override in overrides:
        identifier = override.get("tool_identifier")
        action = override.get("override")
        if not identifier or action not in _OVERRIDE_RANK:
            continue
        rank = _OVERRIDE_RANK[action]
        if rank >= best_rank.get(identifier, 0):
            best_rank[identifier] = rank
            effective[identifier] = "exclude" if action in ("exclude", "suppress", "retire") else action
    kept = [c for c in candidates if effective.get(c.tool_name) != "exclude"]
    pinned = [c for c in kept if effective.get(c.tool_name) == "pin"]
    rest = [c for c in kept if effective.get(c.tool_name) != "pin"]
    return pinned + rest


# A fixed, offline set of representative MCP servers (official + popular), each with
# runnable server_meta. Lets the whole candidates -> safety -> sanction -> export
# journey run with no network and no API key — the substrate for the demo + validation.
_DEMO_SERVERS: tuple[tuple[str, str, dict, list[str]], ...] = (
    (
        "io.modelcontextprotocol/filesystem",
        "Local filesystem access: read, write, and list files in a directory.",
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "env": {},
        },
        ["npm"],
    ),
    (
        "io.modelcontextprotocol/fetch",
        "Fetch a URL and convert the web page to markdown over the network.",
        {"transport": "stdio", "command": "uvx", "args": ["mcp-server-fetch"], "env": {}},
        ["pypi"],
    ),
    (
        "io.modelcontextprotocol/time",
        "Read the current time and convert between timezones. Read-only.",
        {"transport": "stdio", "command": "uvx", "args": ["mcp-server-time"], "env": {}},
        ["pypi"],
    ),
    (
        "io.modelcontextprotocol/sqlite",
        "Query and modify a local SQLite database: read and write rows.",
        {"transport": "stdio", "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "./db.sqlite"], "env": {}},
        ["pypi"],
    ),
    (
        "com.github/github",
        "GitHub issues, pull requests, and code search over an authenticated API.",
        {"transport": "http", "url": "https://api.githubcopilot.com/mcp/", "headers": {}},
        [],
    ),
    (
        "dev.sentry/sentry",
        "Read Sentry errors and monitoring data over the network.",
        {"transport": "http", "url": "https://mcp.sentry.dev/mcp", "headers": {}},
        [],
    ),
)


def demo_mcp_servers() -> list[PackCandidate]:
    """Return the offline demo MCP-server pack (deterministic, no network/keys)."""

    out: list[PackCandidate] = []
    for name, description, meta, extra_tags in _DEMO_SERVERS:
        tags = list(dict.fromkeys(["mcp", *extra_tags, meta["transport"]]))
        out.append(
            PackCandidate(
                pack_slug="mcp",
                tool_name=name,
                state="candidate",
                category="mcp_server",
                description=description,
                tags=tags,
                server_meta=meta,
                consensus_score=0.7,
                freshness_score=0.7,
                independent_source_families=1,
                evidence=[CandidateEvidence(source_family="mcp_registry", source="demo", score=0.7)],
            )
        )
    return out


def _mcp_registry_candidates(pack: ScoutPack) -> list[PackCandidate]:
    try:
        with urllib.request.urlopen(pack.discovery.mcp_registry_url, timeout=8) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    return _parse_registry_payload(
        payload,
        pack_slug=pack.slug,
        source_url=pack.discovery.mcp_registry_url or "mcp_registry",
    )


def _parse_registry_payload(payload: object, *, pack_slug: str, source_url: str) -> list[PackCandidate]:
    """Parse an MCP-registry ``/v0/servers`` payload into enriched candidates.

    Pure + offline (no network) so it is unit-testable. Fails closed: malformed
    entries are skipped, never raised.
    """

    servers = payload.get("servers") if isinstance(payload, dict) else payload
    if not isinstance(servers, list):
        return []
    out: list[PackCandidate] = []
    for server in servers[:50]:
        candidate = _registry_server_to_candidate(server, pack_slug=pack_slug, source_url=source_url)
        if candidate is not None:
            out.append(apply_lifecycle_rules(candidate))
    return out


def _registry_server_to_candidate(server: object, *, pack_slug: str, source_url: str) -> PackCandidate | None:
    if not isinstance(server, dict):
        return None
    name = str(server.get("name") or "").strip()
    if not name:
        repo = server.get("repository")
        if isinstance(repo, dict):
            name = str(repo.get("url") or "").strip()
        elif isinstance(repo, str):
            name = repo.strip()
    if not name:
        name = str(server.get("id") or "").strip()
    if not name:
        return None
    description = str(server.get("description") or "").strip()
    packages = server.get("packages")
    remotes = server.get("remotes")
    tags = ["mcp"]
    if isinstance(packages, list) and packages and isinstance(packages[0], dict):
        server_meta = _stdio_meta_from_package(packages[0])
        registry = str(packages[0].get("registry_name") or packages[0].get("registry") or "").lower()
        if registry:
            tags.append(registry)
        tags.append("stdio")
    elif isinstance(remotes, list) and remotes and isinstance(remotes[0], dict):
        server_meta = _remote_meta(remotes[0])
        tags.append(server_meta["transport"])
    else:
        server_meta = {"transport": "unknown"}
        tags.append("unknown")
    tags = list(dict.fromkeys(tags))  # dedupe, preserve order
    return PackCandidate(
        pack_slug=pack_slug,
        tool_name=name,
        state="candidate",
        category="mcp_server",
        description=description,
        tags=tags,
        server_meta=server_meta,
        evidence=[CandidateEvidence(source_family="mcp_registry", source=source_url or "mcp_registry", score=0.7)],
    )


def _stdio_meta_from_package(pkg: dict) -> dict:
    """Derive a runnable stdio ``server_meta`` from a registry package entry."""

    registry = str(pkg.get("registry_name") or pkg.get("registry") or "").lower()
    pkg_name = str(pkg.get("name") or "").strip()
    runtime_hint = str(pkg.get("runtime_hint") or "").strip()
    env = {
        str(item.get("name")): ""
        for item in (pkg.get("environment_variables") or [])
        if isinstance(item, dict) and item.get("name")
    }
    if registry == "npm":
        command, args = "npx", ["-y", pkg_name]
    elif registry in ("pypi", "pip"):
        command, args = "uvx", [pkg_name]
    elif registry in ("docker", "oci"):
        command, args = "docker", ["run", "-i", "--rm", pkg_name]
    elif runtime_hint:
        command, args = runtime_hint, [pkg_name] if pkg_name else []
    elif pkg_name:
        command, args = pkg_name, []
    else:
        # Nothing runnable derivable — fail closed rather than emit a fake command.
        return {"transport": "unknown"}
    return {"transport": "stdio", "command": command, "args": args, "env": env}


def _remote_meta(remote: dict) -> dict:
    """Derive an http/sse ``server_meta`` from a registry remote entry."""

    transport_type = str(remote.get("transport_type") or remote.get("type") or "").lower()
    transport = "sse" if transport_type == "sse" else "http"
    return {"transport": transport, "url": str(remote.get("url") or "").strip(), "headers": {}}
