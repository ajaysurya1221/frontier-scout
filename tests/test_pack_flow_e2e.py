"""P2-4: the full sanctioned-pack journey, end to end, offline.

TDD (e2e): candidates -> sanction (risk-gated) -> export round-trips into a valid Claude config,
with no network/keys, and writes nothing into the repo (HOME-isolated).
"""

import json

from frontier_scout.cli import main


def test_full_pack_flow_offline(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mcp.json").write_text('{"mcpServers":{}}')
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(home))
    base = ["--repo", str(repo), "--client", "claude-code"]

    # 1. list repo-ranked candidates (offline demo)
    assert main(["packs", "candidates", *base]) == 0
    # 2. sanction a low-risk (read-only) server -> succeeds directly
    assert main(["packs", "sanction", "io.modelcontextprotocol/time", *base]) == 0
    # 3. a high-risk server is BLOCKED without acknowledgement (nonzero exit)
    assert main(["packs", "sanction", "com.github/github", *base]) == 1
    # 3b. ...and sanctions with --acknowledge-risk
    assert main(["packs", "sanction", "io.modelcontextprotocol/filesystem", *base, "--acknowledge-risk"]) == 0

    # 4. export the sanctioned set into Claude config
    target = tmp_path / "export"
    assert main(["packs", "export", "--client", "claude-code", "--target", str(target)]) == 0
    managed = json.loads((target / "managed-settings.json").read_text())
    project = json.loads((target / ".mcp.json").read_text())
    # exactly the two sanctioned servers (time + filesystem); github was blocked
    assert len(project["mcpServers"]) == 2
    assert len(managed["allowedMcpServers"]) == 2
    # HOME isolation: nothing written into the repo working tree
    assert not (repo / "managed-settings.json").exists()
    assert (repo / ".mcp.json").read_text() == '{"mcpServers":{}}'
