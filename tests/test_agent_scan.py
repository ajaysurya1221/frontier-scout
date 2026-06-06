from pathlib import Path

from frontier_scout.agent_firewall.models import ScanResult
from frontier_scout.agent_firewall.scan import scan_repo


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# instructions\n")
    (tmp_path / ".cursorrules").write_text("rules\n")
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {}}\n')
    (tmp_path / ".env").write_text("SECRET_TOKEN=sk-ant-SHOULD-NOT-BE-READ\n")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\n")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_init.sql").write_text("CREATE TABLE x;\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
    pkg = tmp_path / "pyproject.toml"
    pkg.write_text("[project]\nname='x'\n")
    return tmp_path


def test_scan_detects_each_surface_kind(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert isinstance(result, ScanResult)
    kinds = {s.kind for s in result.surfaces}
    assert {"agent-config", "mcp-config", "ci", "secret-likely",
            "protected-path", "deploy-config"} <= kinds
    paths = {s.path for s in result.surfaces}
    assert "CLAUDE.md" in paths and ".cursorrules" in paths
    assert ".env" in paths and ".github/workflows" in {p.rstrip("/") for p in paths} or \
        any(p.startswith(".github") for p in paths)


def test_scan_never_reads_secret_file_contents(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    blob = result.model_dump_json()
    assert "sk-ant-SHOULD-NOT-BE-READ" not in blob
    assert "SECRET_TOKEN" not in blob
    env = next(s for s in result.surfaces if s.path == ".env")
    assert env.kind == "secret-likely" and env.risk == "high"


def test_scan_detects_checks_from_manifests(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert any("pytest" in c for c in result.detected_checks)


def test_scan_counts_by_risk(tmp_path):
    result = scan_repo(str(_make_repo(tmp_path)))
    assert sum(result.counts.values()) == len(result.surfaces)
    assert result.static_only is True
