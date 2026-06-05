"""P1-5: the static safety-summary renderer.

TDD (render + redaction logic): builds a STATIC capability+policy map for an MCP server (no
execution), renders it as markdown labeled "static analysis", redacts secrets, and flags servers
that are high-risk enough to require a sandbox trial before sanction.
"""

from frontier_scout.packs import PackCandidate
from frontier_scout.safety_summary import (
    build_safety_summary,
    is_high_risk,
    render_safety_summary,
)


def test_build_static_safety_summary_classifies_capabilities_and_policy():
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="acme-fs",
        description="Filesystem server that can write files and execute shell commands.",
        category="mcp_server",
        tags=["mcp", "stdio"],
        server_meta={"transport": "stdio", "command": "npx", "args": ["-y", "@acme/fs"]},
    )
    summary = build_safety_summary(cand)
    assert summary["kind"] == "static"
    assert summary["verdict"] in {"adopt", "trial", "assess", "hold"}
    assert "write" in summary["dangerous_flags"] or "shell" in summary["dangerous_flags"]
    assert summary["requires_review"] is True

    rendered = render_safety_summary(summary)
    assert "static analysis" in rendered.lower()
    assert "Capability map" in rendered
    assert "Policy findings" in rendered


def test_render_redacts_secrets():
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="leaky",
        description="Token sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF in the docs.",
        category="mcp_server",
    )
    rendered = render_safety_summary(build_safety_summary(cand))
    assert "sk-ant-api03-AAAABBBB" not in rendered
    assert "REDACTED" in rendered


def test_high_risk_detection_uses_trial_gating_set():
    assert is_high_risk({"dangerous_flags": ["write", "read"]}) is True
    assert is_high_risk({"dangerous_flags": ["read"]}) is False
    # 'unknown' is fail-closed by policy but is not in the trial-gating set.
    assert is_high_risk({"dangerous_flags": ["unknown"]}) is False


def test_summary_carries_load_bearing_verdict_schema_fields():
    cand = PackCandidate(
        pack_slug="mcp",
        tool_name="acme-fs",
        description="Filesystem server.",
        category="mcp_server",
        server_meta={"transport": "stdio", "url": "https://acme.example.com/mcp"},
    )
    summary = build_safety_summary(cand)
    for field in ("category", "risk", "fit", "readiness", "source_url"):
        assert field in summary, f"summary missing load-bearing field: {field}"
    # readiness falls back to the raw verdict tier when no separate tier exists.
    assert summary["readiness"] == summary["verdict"]
    assert summary["source_url"]
