"""P2 foundation: persist enriched candidate fields + a seeded offline demo pack.

TDD: save/list must round-trip ``server_meta``/``category`` (needed by sanction + export across
CLI invocations); the demo pack must be offline and carry runnable ``server_meta``.
"""

from frontier_scout import store
from frontier_scout.packs import PackCandidate, demo_mcp_servers


def test_pack_candidate_persists_enriched_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(
            pack_slug="mcp",
            tool_name="acme",
            state="sanctioned",
            category="mcp_server",
            description="d",
            tags=["mcp", "stdio"],
            server_meta={"transport": "stdio", "command": "npx", "args": ["x"], "env": {}},
        )
    )
    row = next(r for r in store.list_pack_candidates("mcp") if r["tool_name"] == "acme")
    assert row["state"] == "sanctioned"
    assert row["category"] == "mcp_server"
    assert row["server_meta"]["command"] == "npx"
    assert "mcp" in row["tags"]


def test_demo_mcp_servers_are_offline_and_runnable():
    servers = demo_mcp_servers()
    assert 5 <= len(servers) <= 12
    assert all(s.category == "mcp_server" for s in servers)
    assert all(s.server_meta.get("transport") in {"stdio", "http", "sse"} for s in servers)
    # a mix of transports keeps the demo representative
    transports = {s.server_meta["transport"] for s in servers}
    assert {"stdio", "http"} & transports
