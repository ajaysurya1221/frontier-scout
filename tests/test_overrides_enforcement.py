"""P1-4: pack-override enforcement + the extended (pack/client-scoped) adoption_decisions table.

TDD (persistence + precedence): ``exclude`` removes a candidate and ``pin`` reorders it to the
front (precedence exclude>pin>include); a sanction decision round-trips with pack + client; the
previously write-only ``pack_overrides`` table gains a reader.
"""

from frontier_scout import store
from frontier_scout.packs import PackCandidate, apply_pack_overrides


def test_overrides_exclude_removes_and_pin_reorders():
    cands = [PackCandidate(pack_slug="mcp", tool_name=n) for n in ("a", "b", "c")]
    overrides = [
        {"tool_identifier": "b", "override": "exclude"},
        {"tool_identifier": "c", "override": "pin"},
    ]
    names = [c.tool_name for c in apply_pack_overrides(cands, overrides)]
    assert "b" not in names, "exclude must remove"
    assert names == ["c", "a"], "pin must move to front, exclude removes"


def test_exclude_beats_pin_for_same_tool():
    cands = [PackCandidate(pack_slug="mcp", tool_name=n) for n in ("a", "b")]
    overrides = [
        {"tool_identifier": "a", "override": "pin"},
        {"tool_identifier": "a", "override": "exclude"},
    ]
    names = [c.tool_name for c in apply_pack_overrides(cands, overrides)]
    assert names == ["b"], "exclude has precedence over pin"


def test_adoption_decision_round_trips_with_pack_and_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_adoption_decision(
        "acme-mcp",
        "sanctioned",
        pack_slug="mcp",
        client="claude-code",
        approver_label="platform-lead",
        rationale="low risk, repo-relevant",
    )
    rows = store.list_adoption_decisions(pack_slug="mcp")
    assert len(rows) == 1
    row = rows[0]
    assert row["tool_name"] == "acme-mcp"
    assert row["decision"] == "sanctioned"
    assert row["pack_slug"] == "mcp"
    assert row["client"] == "claude-code"
    assert row["approver_label"] == "platform-lead"


def test_list_pack_overrides_reads_back(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    store.save_pack_override("mcp", "acme-mcp", "exclude", reason="deprecated")
    rows = store.list_pack_overrides("mcp")
    assert any(r["tool_identifier"] == "acme-mcp" and r["override"] == "exclude" for r in rows)
