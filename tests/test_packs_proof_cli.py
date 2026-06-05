"""Validation step-2 tooling: `packs proof` renders the A/B/C variants + records a choice.

TDD (CLI behavior): a facilitator can show a partner all three proof variants for a server, then
record which one the partner kept (opt-in telemetry), and read it back via `stats`.
"""

import json

from frontier_scout import telemetry
from frontier_scout.cli import main


def test_proof_shows_three_variants(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mcp.json").write_text('{"mcpServers":{}}')
    rc = main(["packs", "proof", "io.modelcontextprotocol/filesystem", "--repo", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "approve" in out and "static analysis" in out and "static adoption assessment" in out
    assert "partner" not in out  # shipped CLI must not leak the internal design-partner framing


def test_proof_json_returns_all_variants(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "proof", "io.modelcontextprotocol/time", "--repo", str(repo), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data["variants"]) == {"approval_only", "static_safety_summary", "formal_receipt"}


def test_proof_keep_records_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    rc = main(["packs", "proof", "io.modelcontextprotocol/time", "--keep", "static_safety_summary"])
    assert rc == 0
    assert any(
        e["event"] == "proof_variant_kept" and e.get("variant") == "static_safety_summary"
        for e in telemetry.read_events()
    )


def test_proof_unknown_server_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    assert main(["packs", "proof", "does-not-exist", "--repo", str(repo)]) == 1
