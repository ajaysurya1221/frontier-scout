"""Regression tests for code-review findings I-1, I-2, I-3 (and M-3).

Each reproduces a reviewer-reported bug; the fix turns it green.
"""

from frontier_scout import pack_flow, store
from frontier_scout.cli import main
from frontier_scout.exporters import to_project_mcp_json
from frontier_scout.packs import PackCandidate
from frontier_scout.safety_summary import build_safety_summary

_SECRET = "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF"  # pragma: allowlist secret


def test_i1_safety_summary_description_field_is_redacted():
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="leaky",
        category="mcp_server",
        description=f"docs mention {_SECRET} inline",
    )
    summary = build_safety_summary(cand)
    assert _SECRET not in summary["description"]
    assert "REDACTED" in summary["description"]


def test_i1_sanction_json_does_not_leak_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(
            pack_slug="mcp",
            tool_name="leaky",
            category="mcp_server",
            description=f"token {_SECRET}",
            server_meta={"transport": "stdio", "command": "uvx", "args": ["x"], "env": {}},
        )
    )
    # 'leaky' trips the 'credential' capability flag (secret-token text), so sanction is
    # blocked as high-risk and returns 1; the blocked-summary JSON must still be redacted.
    rc = main(["packs", "sanction", "leaky", "--repo", str(tmp_path), "--json"])
    assert rc == 1
    assert _SECRET not in capsys.readouterr().out


def test_i2_exporter_decollides_project_keys():
    a = PackCandidate(
        pack_slug="mcp",
        tool_name="io.acme/github",
        category="mcp_server",
        server_meta={"transport": "http", "url": "https://a.example.com/mcp", "headers": {}},
    )
    b = PackCandidate(
        pack_slug="mcp",
        tool_name="com.evil/github",
        category="mcp_server",
        server_meta={"transport": "http", "url": "https://b.example.com/mcp", "headers": {}},
    )
    out = to_project_mcp_json([a, b])
    assert len(out["mcpServers"]) == 2  # both survive; keys de-collided


def test_i3_sanction_preserves_seeded_scores(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    pack_flow.get_candidates(str(tmp_path), client="claude-code")  # persists demo (scores 0.7)
    pack_flow.sanction_server("io.modelcontextprotocol/time", repo=str(tmp_path), client="claude-code")
    row = next(r for r in store.list_pack_candidates("mcp") if r["tool_name"] == "io.modelcontextprotocol/time")
    assert row["state"] == "sanctioned"
    assert row["freshness_score"] == 0.7
    assert row["consensus_score"] == 0.7


def test_m3_unknown_client_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    # argparse rejects an unsupported client with exit code 2
    import pytest

    with pytest.raises(SystemExit):
        main(["packs", "candidates", "--repo", str(tmp_path), "--client", "claud-code"])
