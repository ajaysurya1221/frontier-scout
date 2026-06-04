"""P2-3: risk-gated sanction.

TDD (business rule): a server with a risky capability flag (write/shell/credential/network) must
NOT sanction until the operator acknowledges the static safety summary; a low/unknown-risk server
sanctions directly; the sanction is persisted as an adoption decision scoped to pack + client.
"""

from frontier_scout import pack_flow, store
from frontier_scout.packs import PackCandidate


def test_high_risk_server_blocks_without_acknowledge(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    # the demo 'filesystem' server can write files -> high risk
    result = pack_flow.sanction_server(
        "io.modelcontextprotocol/filesystem", repo=str(tmp_path), client="claude-code"
    )
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "summary" in result and result["summary"]["requires_trial"] is True


def test_high_risk_server_sanctions_with_acknowledge(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    result = pack_flow.sanction_server(
        "io.modelcontextprotocol/filesystem",
        repo=str(tmp_path),
        client="claude-code",
        acknowledge_risk=True,
        approver="platform-lead",
    )
    assert result["ok"] is True
    decisions = store.list_adoption_decisions(pack_slug="mcp", client="claude-code")
    assert any(
        d["tool_name"] == "io.modelcontextprotocol/filesystem" and d["decision"] == "sanctioned"
        for d in decisions
    )


def test_low_risk_server_sanctions_directly(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(
            pack_slug="mcp",
            tool_name="readonly-docs",
            category="mcp_server",
            description="Read and list documentation pages only.",
            server_meta={"transport": "stdio", "command": "uvx", "args": ["docs-mcp"], "env": {}},
        )
    )
    result = pack_flow.sanction_server("readonly-docs", repo=str(tmp_path), client="claude-code")
    assert result["ok"] is True


def test_unknown_server_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    result = pack_flow.sanction_server("does-not-exist", repo=str(tmp_path), client="claude-code")
    assert result["ok"] is False
    assert "error" in result
