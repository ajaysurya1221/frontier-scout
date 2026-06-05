"""P3-2: the A/B/C proof-variant harness.

TDD (render logic): the same static safety summary renders three distinct ways — approval-only,
sandbox-summary, formal-receipt — so design partners can say which they would keep; the chosen
variant is captured via opt-in telemetry.
"""

from frontier_scout import telemetry
from frontier_scout.packs import PackCandidate
from frontier_scout.proof_variants import VARIANTS, proof_variants, record_preference
from frontier_scout.safety_summary import build_safety_summary


def _summary():
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="acme-fs",
        category="mcp_server",
        description="Filesystem server that can write files.",
    )
    return build_safety_summary(cand)


def test_three_variants_render_distinctly():
    variants = proof_variants(_summary())
    assert set(variants) == set(VARIANTS)
    assert all(text.strip() for text in variants.values())
    # the three faces are genuinely different artifacts
    assert len({text.strip() for text in variants.values()}) == 3
    # FIX 4: the formal variant is a generated STATIC assessment, not a signed/witnessed receipt
    assert "static adoption assessment" in variants["formal_receipt"].lower()
    assert "generated-by" in variants["formal_receipt"].lower()
    assert "signed-by" not in variants["formal_receipt"].lower()
    # FIX 3: the static variant is named for what it is (static safety, not a sandbox)
    assert "static analysis" in variants["static_safety_summary"].lower()
    assert "approve" in variants["approval_only"].lower()


def test_variant_preference_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    assert record_preference("static_safety_summary") is True
    assert any(
        e["event"] == "proof_variant_kept" and e.get("variant") == "static_safety_summary"
        for e in telemetry.read_events()
    )


def test_legacy_sandbox_summary_alias_normalizes(tmp_path, monkeypatch):
    # back-compat: a persisted/legacy "sandbox_summary" is accepted but normalized so
    # no user-facing/recorded artifact shows the misleading "sandbox" name.
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("FRONTIER_SCOUT_TELEMETRY", "1")
    assert record_preference("sandbox_summary") is True
    events = telemetry.read_events()
    assert any(e.get("variant") == "static_safety_summary" for e in events)
    assert not any(e.get("variant") == "sandbox_summary" for e in events)


def test_unknown_variant_rejected():
    import pytest

    with pytest.raises(ValueError):
        record_preference("nonsense")
