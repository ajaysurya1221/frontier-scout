"""P1-2: enrich PackCandidate + the MCP-registry parser.

TDD (parsing behavior): a registry payload must produce candidates carrying ``category``,
``description``, ``tags`` and a runnable ``server_meta`` (transport + command/args/env or url),
fail closed on bad data, and leave the offline (``discover=False``) seed path unchanged.
"""

from frontier_scout import packs
from frontier_scout.packs import candidate_rows_for_pack, default_packs

PAYLOAD = {
    "servers": [
        {
            "name": "io.github.acme/filesystem",
            "description": "Local filesystem access for agents.",
            "repository": {"url": "https://github.com/acme/filesystem", "source": "github"},
            "packages": [
                {
                    "registry_name": "npm",
                    "name": "@acme/mcp-filesystem",
                    "version": "1.2.0",
                    "environment_variables": [{"name": "ROOT_DIR", "description": "root"}],
                }
            ],
        },
        {
            "name": "io.github.acme/sentry",
            "description": "Sentry error monitoring.",
            "remotes": [{"transport_type": "streamable", "url": "https://mcp.sentry.dev/mcp"}],
        },
        {"description": "no name -> skipped"},
    ]
}


def test_parse_registry_payload_enriches_candidates():
    cands = packs._parse_registry_payload(PAYLOAD, pack_slug="mcp", source_url="u")
    assert len(cands) == 2, "the nameless server must be skipped"
    by_name = {c.tool_name: c for c in cands}

    fs = by_name["io.github.acme/filesystem"]
    assert fs.category == "mcp_server"
    assert "filesystem" in fs.description.lower()
    assert fs.server_meta["transport"] == "stdio"
    assert fs.server_meta["command"] == "npx"
    assert "@acme/mcp-filesystem" in fs.server_meta["args"]
    assert "ROOT_DIR" in fs.server_meta["env"]
    assert "mcp" in fs.tags

    sentry = by_name["io.github.acme/sentry"]
    assert sentry.server_meta["transport"] == "http"
    assert sentry.server_meta["url"] == "https://mcp.sentry.dev/mcp"


def test_parse_registry_payload_fails_closed_on_bad_data():
    assert packs._parse_registry_payload(None, pack_slug="mcp", source_url="u") == []
    assert packs._parse_registry_payload({"servers": "garbage"}, pack_slug="mcp", source_url="u") == []
    assert packs._parse_registry_payload({"servers": [42, "x"]}, pack_slug="mcp", source_url="u") == []


def test_discover_false_returns_only_seeds_offline():
    pack = default_packs()["mcp"]
    cands = candidate_rows_for_pack(pack, discover=False)
    assert cands, "the mcp pack has seed repos"
    assert len(cands) == len(pack.seed_repos)
    assert all(c.state == "core" for c in cands)
    # additive enrichment fields default cleanly on seed candidates
    assert all(c.category is None and c.server_meta == {} for c in cands)
