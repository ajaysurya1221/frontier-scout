"""Scout detail matches the prototype: Permission map present, the legacy
inline "Why it matters" / "Unknowns" sections gone (handoff §4)."""

import asyncio

from textual.widgets import Static

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.state import Verdict


def _run(coro):
    return asyncio.run(coro)


def _tool_verdict(**over):
    base = dict(
        tool_name="x/y", verdict="trial", fit="high", risk="medium",
        category="MCP Server", source_url="https://github.com/x/y",
        what="does things", why_it_matters="legacy matters text",
        fit_reasons=["fits a", "fits b"], concerns=[], next_safe_step="trial it",
        unknowns=["legacy unknown text"],
        permission_manifest={"capabilities": {
            "filesystem": "likely", "network": "possible",
            "shell": "likely", "secrets": "unlikely"}},
    )
    base.update(over)
    return Verdict.from_payload(base)


def test_verdict_projects_capabilities_from_manifest():
    v = _tool_verdict()
    assert dict(v.capabilities) == {
        "filesystem": "likely", "network": "possible",
        "shell": "likely", "secrets": "unlikely",
    }


def test_dep_verdict_has_no_capabilities():
    v = Verdict.from_payload({
        "tool_name": "pkg", "verdict": "adopt", "fit": "high", "risk": "low",
        "category": "dep", "source_url": "", "what": "", "why_it_matters": "",
        "fit_reasons": [], "concerns": [], "next_safe_step": "",
        "from_version": "1", "to_version": "2",
    }, kind="dep")
    assert v.capabilities == ()


def _pane_text(app) -> str:
    out = []
    for w in app.query(Static):
        c = getattr(w, "content", None)
        if c is None:
            r = getattr(w, "renderable", None)
            c = getattr(r, "plain", r)
        out.append(str(c))
    return "\n".join(out)


def test_detail_renders_permission_map_and_drops_legacy_sections():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            v = _tool_verdict()
            app.state = app.state.with_(tab="scout", scope="all", verdicts=(v,), sel=0)
            await app._render_pane()
            await pilot.pause()
            txt = _pane_text(app)
            assert "Permission map" in txt, "permission map not rendered for a tool verdict"
            assert "shell" in txt and "filesystem" in txt, "capability rows missing"
            assert "Why it matters" not in txt, "legacy 'Why it matters' should be gone"
            assert "Unknowns" not in txt, "inline 'Unknowns' should be gone"

    _run(go())


def test_detail_no_permission_map_for_dep():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            v = Verdict.from_payload({
                "tool_name": "langchain-core", "verdict": "adopt", "fit": "high",
                "risk": "low", "category": "dep", "source_url": "",
                "what": "upgrade", "why_it_matters": "", "fit_reasons": ["safe minor"],
                "concerns": [], "next_safe_step": "", "from_version": "0.1",
                "to_version": "0.2", "classification": "minor",
            }, kind="dep")
            app.state = app.state.with_(tab="scout", scope="all", verdicts=(v,), sel=0)
            await app._render_pane()
            await pilot.pause()
            txt = _pane_text(app)
            assert "Permission map" not in txt, "deps must not render a permission map"

    _run(go())
