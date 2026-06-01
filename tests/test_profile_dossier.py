import json
from pathlib import Path

from frontier_scout.dossier import build_dossier
from frontier_scout.profile import build_scout_profile, export_profile
from frontier_scout.scout import run_scan
from frontier_scout.store import init_db, latest_repo_profile, save_repo_profile
from frontier_scout.trials import run_trial


def test_profile_detects_repo_signals_without_reading_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "next": "latest",
                    "@modelcontextprotocol/sdk": "latest",
                }
            }
        )
    )
    (repo / "Dockerfile").write_text("FROM python:3.11\n")
    (repo / ".mcp.json").write_text("{}\n")
    (repo / ".env.local").write_text("ANTHROPIC_API_KEY=secret\n")

    profile = build_scout_profile(repo)
    save_repo_profile(profile)
    export_path = export_profile(profile, tmp_path / "profile.json")
    payload = json.loads(export_path.read_text())

    assert "javascript/typescript" in profile.languages
    assert "@modelcontextprotocol/sdk" in profile.ai_tooling
    assert "agent-config-present" in profile.risk_flags
    assert ".env.local" in profile.ignored_paths
    assert "secret" not in export_path.read_text()
    assert latest_repo_profile(str(repo))["repo_id"] == payload["repo_id"]


def test_scan_personalizes_same_seed_verdict_for_agent_repo(tmp_path):
    repo = tmp_path / "agent-repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# local agents\n")
    (repo / ".mcp.json").write_text("{}\n")

    payload = run_scan(repo=repo, dry_run=True, persist=False)
    mcp = next(v for v in payload["verdicts"] if v["tool_name"] == "modelcontextprotocol/servers")

    assert mcp["fit"] == "high"
    assert "matches existing MCP/agent configuration" in mcp["fit_reasons"]
    assert "runtime permission surface needs explicit review" in mcp["unknowns"]


def test_scan_does_not_fake_high_fit_for_unrelated_repo(tmp_path):
    repo = tmp_path / "plain-rust"
    repo.mkdir()
    (repo / "Cargo.toml").write_text("[package]\nname='plain'\nversion='0.1.0'\n")

    payload = run_scan(repo=repo, dry_run=True, persist=False)
    mcp = next(v for v in payload["verdicts"] if v["tool_name"] == "modelcontextprotocol/servers")

    assert mcp["fit"] == "medium"
    assert "no strong local stack match detected" in mcp["fit_reasons"]


def test_dossier_includes_gap_analysis_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# local agents\n")
    init_db()

    payload = build_dossier("https://github.com/modelcontextprotocol/servers", repo=repo)

    assert payload["tool_name"] == "modelcontextprotocol/servers"
    # The MCP servers repo has a permission surface that requires a stored
    # sandbox receipt, so with no trial on record the deterministic verdict is
    # "trial" (not the weaker "in {all four verdicts}" tautology, which could
    # never fail). If the policy engine ever silently downgrades this to
    # adopt/assess/hold, this assertion catches it.
    assert payload["verdict"] == "trial"
    assert any("trial receipt" in gap for gap in payload["unknowns"])
    assert Path(payload["receipt_path"]).exists()
    assert "Permission map" in Path(payload["receipt_path"]).read_text()


def test_trial_report_only_sandbox_writes_non_executing_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))

    result = run_trial(
        "browser-use/browser-use",
        url="https://github.com/browser-use/browser-use",
        dry_run=True,
    )

    assert result["lab_result"]["status"] == "skipped"
    assert "no subprocess executed" in result["lab_result"]["summary"].lower()
