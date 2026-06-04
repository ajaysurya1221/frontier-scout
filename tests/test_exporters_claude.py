"""P2-1: the Claude Code managed-config + project exporter.

TDD (export logic): a sanctioned server set must render to (1) a managed
``allowedMcpServers``/``deniedMcpServers`` fragment and (2) a project ``.mcp.json`` map that match
the golden Spike-B fixtures byte-for-structure; unsanctioned servers land in ``deniedMcpServers``;
and any emitted secret is redacted.
"""

import json
from pathlib import Path

from frontier_scout.exporters import (
    export_claude_config,
    to_managed_config,
    to_project_mcp_json,
)
from frontier_scout.packs import PackCandidate

FIXTURES = Path(__file__).parent / "fixtures"

GITHUB = PackCandidate(
    pack_slug="mcp",
    tool_name="github",
    category="mcp_server",
    server_meta={"transport": "http", "url": "https://api.githubcopilot.com/mcp/", "headers": {}},
)
FILESYSTEM = PackCandidate(
    pack_slug="mcp",
    tool_name="filesystem",
    category="mcp_server",
    server_meta={
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "env": {},
    },
)


def test_managed_config_matches_fixture():
    managed = to_managed_config([GITHUB, FILESYSTEM], denied=["dangerous-server"])
    assert managed == json.loads((FIXTURES / "claude_config_managed.json").read_text())


def test_project_config_matches_fixture():
    project = to_project_mcp_json([GITHUB, FILESYSTEM])
    assert project == json.loads((FIXTURES / "claude_config_project.json").read_text())


def test_export_writes_both_faces_and_redacts(tmp_path):
    leaky = PackCandidate(
        pack_slug="mcp",
        tool_name="leaky",
        category="mcp_server",
        server_meta={
            "transport": "stdio",
            "command": "npx",
            "args": ["pkg"],
            "env": {"API_KEY": "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF"},
        },
    )
    paths = export_claude_config([leaky], denied=[], target_dir=tmp_path)
    managed_text = Path(paths["managed"]).read_text()
    project_text = Path(paths["project"]).read_text()
    # both files are valid JSON
    json.loads(managed_text)
    json.loads(project_text)
    # the planted secret is redacted in the written file
    assert "sk-ant-api03-AAAABBBB" not in project_text
    assert "REDACTED" in project_text
