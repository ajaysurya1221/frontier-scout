"""Living Scout Pack definitions and deterministic lifecycle rules."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

PackState = Literal["candidate", "watched", "core", "retired"]
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


def candidate_rows_for_pack(pack: ScoutPack, *, discover: bool = False) -> list[PackCandidate]:
    """Return seed and optional live-discovered candidates for a pack."""

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
    return candidates


def _mcp_registry_candidates(pack: ScoutPack) -> list[PackCandidate]:
    try:
        with urllib.request.urlopen(pack.discovery.mcp_registry_url, timeout=8) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    servers = payload.get("servers") if isinstance(payload, dict) else payload
    if not isinstance(servers, list):
        return []
    candidates: list[PackCandidate] = []
    for server in servers[:50]:
        if not isinstance(server, dict):
            continue
        name = str(server.get("repository") or server.get("name") or server.get("id") or "").strip()
        if not name:
            continue
        candidates.append(
            apply_lifecycle_rules(
                PackCandidate(
                    pack_slug=pack.slug,
                    tool_name=name,
                    state="candidate",
                    evidence=[
                        CandidateEvidence(
                            source_family="mcp_registry",
                            source=pack.discovery.mcp_registry_url or "mcp_registry",
                            score=0.7,
                        )
                    ],
                )
            )
        )
    return candidates
