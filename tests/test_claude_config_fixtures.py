"""Spike B (P0-4): the Claude Code config fixtures must match the documented shape.

These golden fixtures pin the exact JSON the managed-config exporter (P2-1) has to emit, taken
from the live Claude Code docs (see ``docs/spike-claude-config.md``). This is a data-validation
test, not red-green-refactor TDD (the fixtures *are* the artifact) — it guards against drift.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_project_fixture_matches_mcp_json_shape():
    cfg = _load("claude_config_project.json")
    assert set(cfg) == {"mcpServers"}
    servers = cfg["mcpServers"]
    assert servers, "expected at least one server"
    for name, spec in servers.items():
        assert isinstance(name, str) and name
        # stdio: requires a command; http: requires type==http + url.
        if spec.get("type") == "http":
            assert spec.get("url", "").startswith("http")
        else:
            assert spec.get("command"), f"stdio server {name} needs a command"
            assert isinstance(spec.get("args", []), list)
            assert isinstance(spec.get("env", {}), dict)


def test_managed_fixture_matches_allow_deny_shape():
    cfg = _load("claude_config_managed.json")
    assert isinstance(cfg.get("allowManagedMcpServersOnly"), bool)
    for key in ("allowedMcpServers", "deniedMcpServers"):
        entries = cfg[key]
        assert isinstance(entries, list)
        for entry in entries:
            # Each entry is an object with exactly one matcher key.
            assert isinstance(entry, dict) and len(entry) == 1
            (matcher,) = entry.keys()
            assert matcher in {"serverUrl", "serverCommand", "serverName"}
            if matcher == "serverCommand":
                assert isinstance(entry[matcher], list)
            else:
                assert isinstance(entry[matcher], str)
