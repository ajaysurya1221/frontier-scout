# tests/test_claude_config_names.py
from frontier_scout.exporters.claude_config import to_managed_config_from_names


def test_managed_config_from_names_shape():
    cfg = to_managed_config_from_names(["github", "notion"], denied=["evilserver"])
    assert cfg["allowManagedMcpServersOnly"] is True
    assert cfg["allowedMcpServers"] == [{"serverName": "github"}, {"serverName": "notion"}]
    assert cfg["deniedMcpServers"] == [{"serverName": "evilserver"}]


def test_managed_config_from_names_empty_allowlist():
    cfg = to_managed_config_from_names([])
    assert cfg["allowedMcpServers"] == []
    assert cfg["deniedMcpServers"] == []


def test_managed_config_from_names_can_disable_managed_only():
    cfg = to_managed_config_from_names(["github"], allow_managed_only=False)
    assert cfg["allowManagedMcpServersOnly"] is False
