import json
import sqlite3
from pathlib import Path

from frontier_scout.cli import main
from frontier_scout.dep_trial import run_dependency_trial
from frontier_scout.dependencies import (
    classify_release_notes,
    run_dependency_scan,
)
from frontier_scout.packs import (
    CandidateEvidence,
    PackCandidate,
    apply_lifecycle_rules,
    default_packs,
)
from frontier_scout.profile import build_scout_profile
from frontier_scout.store import db_path, init_db, list_pack_candidates, list_packs


def test_default_packs_are_living_seed_definitions():
    packs = default_packs()

    assert "mcp" in packs
    assert "security-risky-tools" not in packs
    assert "modelcontextprotocol/servers" in packs["mcp"].seed_repos
    assert packs["mcp"].discovery.github_queries
    assert packs["mcp"].discovery.hn_keywords


def test_pack_lifecycle_promotes_deduped_consensus_and_retires_stale_core():
    candidate = PackCandidate(
        pack_slug="mcp",
        tool_name="example/new-mcp",
        state="candidate",
        evidence=[
            CandidateEvidence(source_family="hn", source="hn", score=0.6, days_ago=0),
            CandidateEvidence(source_family="hn", source="reddit", score=0.6, days_ago=0),
            CandidateEvidence(source_family="mcp_registry", source="registry", score=0.6, days_ago=0),
        ],
    )

    promoted = apply_lifecycle_rules(candidate)

    assert promoted.state == "watched"
    assert promoted.consensus_score >= 0.6
    assert promoted.independent_source_families == 2

    stale = PackCandidate(
        pack_slug="mcp",
        tool_name="legacy/old-server",
        state="core",
        days_since_release=200,
        issue_response_p90_days=35,
        star_growth_z=-1.5,
    )

    assert apply_lifecycle_rules(stale).state == "retired"


def test_profile_extracts_python_and_node_dependency_versions(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("langchain-core==1.3.5\npytesseract>=0.3\n")
    (repo / "package.json").write_text(
        json.dumps({"dependencies": {"@modelcontextprotocol/sdk": "^1.2.0", "next": "15.0.0"}})
    )
    (repo / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/@modelcontextprotocol/sdk": {"version": "1.2.3"},
                    "node_modules/next": {"version": "15.0.1"},
                },
            }
        )
    )

    profile = build_scout_profile(repo)
    deps = {(d.ecosystem, d.name): d for d in profile.dependencies}

    assert deps[("pypi", "langchain-core")].specifier == "==1.3.5"
    assert deps[("pypi", "langchain-core")].resolved_version == "1.3.5"
    assert deps[("npm", "@modelcontextprotocol/sdk")].specifier == "^1.2.0"
    assert deps[("npm", "@modelcontextprotocol/sdk")].resolved_version == "1.2.3"


def test_release_note_classifier_carves_out_hardening_from_noise():
    result = classify_release_notes(
        package_name="langchain-core",
        from_version="1.3.5",
        to_version="1.4.0",
        text=(
            "## Security\n"
            "Harden load() against untrusted manifests. "
            "Update urllib3 dependency constraints."
        ),
    )

    assert result.classification == "hardening"
    assert result.confidence >= 0.6
    assert any("untrusted manifests" in quote for quote in result.evidence_quotes)


def test_dependency_scan_uses_fixture_metadata_and_persists_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# agents\n")
    (repo / "requirements.txt").write_text("langchain-core==1.3.5\n")
    fixtures = {
        "pypi": {
            "langchain-core": {
                "latest_version": "1.4.0",
                "release_notes": {
                    "1.4.0": "## Security\nHarden load() against untrusted manifests."
                },
            }
        },
        "osv": {"PyPI:langchain-core:1.3.5": {"vulns": [{"id": "GHSA-test-123"}]}},
    }

    payload = run_dependency_scan(repo, metadata=fixtures)

    assert payload["findings"][0]["package_name"] == "langchain-core"
    assert payload["findings"][0]["classification"] == "hardening"
    assert payload["findings"][0]["verdict"] == "trial"
    assert payload["findings"][0]["advisory_ids"] == ["GHSA-test-123"]

    with sqlite3.connect(db_path()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dependency_findings").fetchone()[0]
    assert count == 1


def test_dependency_scan_degrades_on_missing_registry_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("unknown-ai-package==0.1.0\n")

    payload = run_dependency_scan(repo, metadata={"pypi": {}, "osv": {}})

    assert payload["findings"][0]["package_name"] == "unknown-ai-package"
    assert payload["findings"][0]["classifier_confidence"] == 0
    assert payload["findings"][0]["verdict"] == "assess"


def test_dependency_trial_uses_temp_directory_without_mutating_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    manifest = repo / "requirements.txt"
    manifest.write_text("langchain-core==1.3.5\n")

    result = run_dependency_trial(
        "langchain-core",
        from_version="1.3.5",
        to_version="1.4.0",
        repo=repo,
        dry_run=True,
    )

    assert manifest.read_text() == "langchain-core==1.3.5\n"
    assert result["lab_result"]["status"] == "skipped"
    assert "temp" in result["lab_result"]["summary"].lower()
    assert Path(result["receipt_path"]).exists()


def test_packs_and_deps_cli_smoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("langchain-core==1.3.5\n")

    assert main(["packs", "list"]) == 0
    assert "mcp" in capsys.readouterr().out

    assert main(["packs", "show", "mcp"]) == 0
    assert "modelcontextprotocol/servers" in capsys.readouterr().out

    assert main(["profile", "--repo", str(repo), "--dependencies", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dependencies"][0]["name"] == "langchain-core"

    assert main(["deps", "scan", "--repo", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repo"] == str(repo.resolve())

    init_db()
    assert list_packs()
    assert list_pack_candidates() == []
