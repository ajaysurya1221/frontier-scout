"""Hardening from CodeRabbit review on PR #43 — verified category-1 fixes only.

Security + correctness + fail-closed robustness on the sanctioned-pack surfaces. No new
features; each test pins a real defect CodeRabbit flagged (credential leak, --json paths,
fail-closed registry parsing, malformed-data robustness).
"""

import json

from frontier_scout import telemetry
from frontier_scout.cli import main
from frontier_scout.exporters.claude_config import to_managed_config, to_project_mcp_json
from frontier_scout.packs import PackCandidate, _stdio_meta_from_package


def _http(url, headers=None):
    meta = {"transport": "http", "url": url}
    if headers is not None:
        meta["headers"] = headers
    return PackCandidate(pack_slug="mcp", tool_name="x/remote", category="mcp_server", server_meta=meta)


# A — credentials in a server URL must never reach the exported serverUrl wildcard.
def test_export_strips_url_credentials():
    managed = to_managed_config([_http("https://alice:s3cret@api.example.com/mcp")])
    blob = json.dumps(managed)
    assert "s3cret" not in blob and "alice" not in blob
    assert "api.example.com" in blob  # host preserved


# B — malformed (non-mapping) headers must not crash the project export.
def test_export_tolerates_non_dict_headers():
    project = to_project_mcp_json([_http("https://api.example.com/mcp", headers="not-a-dict")])
    entry = next(iter(project["mcpServers"].values()))
    assert "headers" not in entry  # dropped, not crashed


# C — a known registry with a missing package name must fail closed (no fake command).
def test_stdio_meta_fails_closed_on_missing_package_name():
    assert _stdio_meta_from_package({"registry_name": "npm", "name": ""}) == {"transport": "unknown"}
    assert _stdio_meta_from_package({"registry_name": "docker", "name": ""}) == {"transport": "unknown"}
    # a present name still derives a runnable command
    assert _stdio_meta_from_package({"registry_name": "npm", "name": "pkg"})["command"] == "npx"


# E — legacy `packs candidates --json` (no --repo) must emit valid JSON, not text.
def test_legacy_candidates_json_is_machine_readable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    rc = main(["packs", "candidates", "--json"])
    assert rc == 0
    json.loads(capsys.readouterr().out)  # must parse (empty store -> [])


# F — `packs proof --json` must stay machine-readable on failure.
def test_proof_json_failure_is_machine_readable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "proof", "does-not-exist", "--repo", str(repo), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)  # must parse even on failure
    assert payload.get("ok") is False


# G — a valid-JSON-but-non-dict telemetry line must not crash read_events/summarize.
def test_telemetry_tolerates_non_dict_event_line(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    telemetry.record_event("candidates_viewed", count=1)
    telemetry.events_path().open("a", encoding="utf-8").write("42\n")  # corrupt/non-object line
    events = telemetry.read_events()
    assert all(isinstance(e, dict) for e in events)
    telemetry.summarize()  # must not raise
