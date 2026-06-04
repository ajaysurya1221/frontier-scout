"""P2-2: `packs candidates --repo --client` CLI surface.

TDD (CLI behavior): repo-ranked candidates render (JSON + text), offline with --demo, each
carrying repo_fit + a static-safety read.
"""

import json

from frontier_scout.cli import main


def test_candidates_repo_client_demo_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mcp.json").write_text('{"mcpServers":{}}')
    rc = main(["packs", "candidates", "--repo", str(repo), "--client", "claude-code", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list) and len(out) >= 5
    assert all("tool_name" in c and "repo_fit" in c and "requires_trial" in c for c in out)


def test_candidates_text_output_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "candidates", "--repo", str(repo), "--client", "claude-code"])
    assert rc == 0
    assert "mcp" in capsys.readouterr().out.lower()
