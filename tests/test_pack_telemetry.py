"""P3-1: local, opt-in usage telemetry + the `stats` funnel.

TDD (instrumentation logic): events append ONLY when opted in (off by default); secrets are
redacted; the path makes NO network call; `stats` aggregates the validation funnel.
"""

import json

from frontier_scout import telemetry


def test_telemetry_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.delenv("FRONTIER_SCOUT_TELEMETRY", raising=False)
    assert telemetry.is_enabled() is False
    assert telemetry.record_event("sanctioned", server="x") is False
    assert not telemetry.events_path().exists()


def test_telemetry_records_and_summarizes_when_opted_in(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    assert telemetry.record_event("candidates_viewed", count=6, client="claude-code") is True
    assert telemetry.record_event("sanctioned", server="acme", client="claude-code") is True
    assert len(telemetry.read_events()) == 2
    summary = telemetry.summarize()
    assert summary["candidates_viewed"] == 1
    assert summary["sanctioned"] == 1
    assert summary["enabled"] is True


def test_telemetry_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    telemetry.record_event("sanctioned", reason="key sk-ant-api03-AAAABBBBCCCCDDDDEEEE")
    raw = telemetry.events_path().read_text()
    assert "sk-ant-api03-AAAA" not in raw
    assert "REDACTED" in raw


def test_telemetry_makes_no_network_call(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    import urllib.request

    def _boom(*a, **k):
        raise AssertionError("network call in telemetry path")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert telemetry.record_event("exported", client="claude-code") is True


def test_stats_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    telemetry.record_event("sanctioned", server="x")
    from frontier_scout.cli import main

    assert main(["stats", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sanctioned"] == 1
