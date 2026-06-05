"""Claim-honesty hardening sprint: user-facing strings must not overclaim.

These tests pin the honesty boundary the sprint enforces — Claude-Code-only export,
static-only safety language (no "trial"/execution implication), generated (not signed)
artifacts, a labelled verdict, and an honest export disclaimer. Copy/label-level only;
no behavior change beyond refusing to emit Claude config under another client's name.
"""

import json

from frontier_scout import pack_flow, store
from frontier_scout.cli import main
from frontier_scout.packs import PackCandidate
from frontier_scout.safety_summary import build_safety_summary


# ── FIX 1 — client-scope honesty ────────────────────────────────────────────
def test_client_claude_code_candidates_work(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "candidates", "--repo", str(repo), "--client", "claude-code"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_client_copilot_is_hard_gated_and_emits_no_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    target = tmp_path / "out"
    rc = main(["packs", "export", "--client", "copilot", "--target", str(target)])
    captured = capsys.readouterr()
    assert rc != 0
    assert "not implemented" in captured.err.lower()
    assert "roadmap" in captured.err.lower()
    # never emit Claude config under a Copilot label
    assert "allowedMcpServers" not in captured.out
    assert not (target / "managed-settings.json").exists()


def test_client_cursor_candidates_hard_gated(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "candidates", "--repo", str(repo), "--client", "cursor"])
    captured = capsys.readouterr()
    assert rc != 0
    assert "not implemented" in captured.err.lower()
    assert "fit=" not in captured.out  # no candidate list leaked under a cursor label


# ── FIX 2 — no "trial" wording for static analysis ──────────────────────────
def test_candidates_text_drops_trial_wording_and_states_static(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = main(["packs", "candidates", "--repo", str(repo), "--client", "claude-code"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[trial required]" not in out
    assert "no mcp server was executed" in out.lower()
    # the demo filesystem server is high-risk -> shows the honest static review flag
    assert "needs review" in out.lower()


def test_summary_uses_requires_review_not_requires_trial(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="acme-fs",
        category="mcp_server",
        description="Filesystem server that can write files.",
    )
    summary = build_safety_summary(cand)
    assert "requires_review" in summary
    assert "requires_trial" not in summary


# ── FIX 5 — verdict parenthetical is labelled, not bare "(assess)" ───────────
def test_sanction_output_labels_the_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(
            pack_slug="mcp",
            tool_name="readonly-docs",
            category="mcp_server",
            description="Read and list documentation pages only.",
            server_meta={"transport": "stdio", "command": "uvx", "args": ["docs-mcp"], "env": {}},
        )
    )
    rc = main(["packs", "sanction", "readonly-docs", "--repo", str(tmp_path), "--client", "claude-code"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "verdict:" in out  # not an undefined bare "(assess)"


# ── FIX 6 — export value-prop / honesty line + valid JSON ───────────────────
def test_export_prints_static_disclaimer_and_writes_valid_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_candidate(
        PackCandidate(
            pack_slug="mcp",
            tool_name="readonly-docs",
            category="mcp_server",
            description="Read and list documentation pages only.",
            server_meta={"transport": "stdio", "command": "uvx", "args": ["docs-mcp"], "env": {}},
        )
    )
    pack_flow.sanction_server("readonly-docs", repo=str(tmp_path), client="claude-code")
    target = tmp_path / "out"
    rc = main(["packs", "export", "--client", "claude-code", "--target", str(target)])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "static export" in out and "not runtime enforcement" in out
    # the generated JSON stays valid + unaffected by the explanatory text
    managed = json.loads((target / "managed-settings.json").read_text())
    assert "allowedMcpServers" in managed
