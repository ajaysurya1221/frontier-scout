"""P1-3: wire the repo-aware fit scorer into pack candidates.

TDD (ranking logic): for a repo that uses Claude Code + MCP, MCP-relevant servers must rank above
unrelated tools; the adapter must turn a PackCandidate into the ``(category, text, stack)`` shape
``evaluate._fit`` expects; ranking must be deterministic; and the no-profile path is unchanged.
"""

from frontier_scout.packs import (
    PackCandidate,
    candidate_rows_for_pack,
    default_packs,
    pack_candidate_to_fit_input,
    rank_candidates_for_repo,
)
from frontier_scout.profile import ScoutProfile


def _c(name, category=None, description="", tags=()):
    return PackCandidate(
        pack_slug="mcp",
        tool_name=name,
        category=category,
        description=description,
        tags=list(tags),
        consensus_score=0.5,
    )


def _claude_repo_profile():
    return ScoutProfile(
        repo="t", repo_id="t", languages=["python"], agent_configs=["claude", ".mcp.json"]
    )


def test_mcp_relevant_servers_rank_higher_for_claude_repo():
    cands = [
        _c("z-unrelated-linter", category="dev_tool", description="a CLI linter"),
        _c("acme-mcp-server", category="mcp_server", description="MCP server for agents", tags=["mcp", "stdio"]),
    ]
    ranked = rank_candidates_for_repo(cands, _claude_repo_profile())
    assert ranked[0].tool_name == "acme-mcp-server"
    assert ranked[0].repo_fit == "high"


def test_pack_candidate_to_fit_input_builds_category_and_text():
    c = _c("x-mcp", category="mcp_server", description="desc text", tags=["mcp", "stdio"])
    category, text, stack = pack_candidate_to_fit_input(c, {"languages": ["python"]})
    assert category == "mcp_server"
    assert "x-mcp" in text and "mcp" in text and "desc" in text
    assert stack == {"languages": ["python"]}


def test_ranking_is_deterministic():
    profile = _claude_repo_profile()
    cands = [_c(f"s{i}", category="mcp_server", description="mcp", tags=["mcp"]) for i in range(4)]
    r1 = [c.tool_name for c in rank_candidates_for_repo(cands, profile)]
    r2 = [c.tool_name for c in rank_candidates_for_repo(cands, profile)]
    assert r1 == r2


def test_candidate_rows_for_pack_unchanged_without_profile():
    # back-compat characterization: no profile -> no repo_fit set, seeds only.
    pack = default_packs()["mcp"]
    rows = candidate_rows_for_pack(pack, discover=False)
    assert rows
    assert all(c.repo_fit is None for c in rows)
