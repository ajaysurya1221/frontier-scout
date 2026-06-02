"""§11.1 acceptance: the `r` key MUST scan on Deps, Guard, and Settings.

This locks the headline regression from the handoff (Bug #1): the empty state on
each of these tabs advertises ``r`` and ``r`` must run the scan via the SAME path
a click will use — ``action_refresh`` → ``_refresh_worker(tab)`` → ``WorkDone`` →
``state.with_(<cache>=payload)`` → re-render. We also assert the empty-state copy
still exists for the pre-load frame (Bug #2: auto-load must not delete the ``r``
affordance).

Every backend call is stubbed via the ``frontier_scout.tui3.data`` module (the app
imports it by reference), so nothing here spends, hits the network, or scans the
real filesystem.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import MissionControlApp


def _run(coro):
    return asyncio.run(coro)


@contextmanager
def _patch(**stubs):
    """Swap several ``data`` attributes for record-only stubs, then restore."""
    orig = {name: getattr(data, name) for name in stubs}
    for name, stub in stubs.items():
        setattr(data, name, stub)
    try:
        yield
    finally:
        for name, fn in orig.items():
            setattr(data, name, fn)


class _Stub:
    def __init__(self, ret):
        self.ret = ret
        self.calls = 0

    def __call__(self, *a, **k):
        self.calls += 1
        return self.ret


def _pane_text(app) -> str:
    """Concatenate the markup of every Static on screen.

    In this Textual build a ``Static``'s text lives in ``.content`` (the markup
    string); ``.renderable`` is ``None``. Fall back through ``renderable`` for
    any other widget kind.
    """
    parts = []
    for w in app.query("Static"):
        c = getattr(w, "content", None)
        if c:
            parts.append(str(c))
            continue
        r = getattr(w, "renderable", "")
        parts.append(getattr(r, "plain", None) or str(r))
    return "  ".join(parts)


# Fixture payloads shaped like the real data.py projections ------------------
_DEPS = [
    {
        "tool_name": "langchain-core",
        "from_version": "1.2.0",
        "to_version": "1.3.5",
        "classification": "security",
        "why": "patches an advisory you import",
        "verdict": "trial",
    }
]
_GUARD = {
    "findings": [
        {
            "severity": "high", "tool": "acme", "rule": "no-receipt",
            "detail": "no trial receipt", "fix": "frontier-scout trial acme",
        }
    ],
    "high": 1,
    "medium": 0,
    "fail": True,
}
_POLICY = {"strict": False, "fail_unknown_capabilities": True}
_PROFILE = {"languages": ["python"], "frameworks": [], "managers": ["pip"], "agent_configs": [], "risk_flags": []}
_DOCTOR = [{"name": "home", "status": "ok", "detail": "~/.frontier-scout", "fix": ""}]


def test_r_scans_on_deps():
    deps = _Stub(_DEPS)

    async def go():
        app = MissionControlApp(demo=True)
        with _patch(dependencies=deps):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Open Deps (key 6). Auto-load fires the worker on first open.
                await pilot.press("6")
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.tab == "deps"
                assert app.state.deps_cache is not None, "auto-load did not populate deps_cache"
                first = deps.calls
                assert first >= 1, "auto-load never called data.dependencies"

                # Simulate the pre-load (fresh) frame: cache None → empty state.
                app.state = app.state.with_(deps_cache=None)
                await app._render_pane()
                await pilot.pause()
                txt = _pane_text(app)
                assert "No dependency scan yet" in txt, txt
                assert "to scan your manifests" in txt, txt

                # Press r → must re-run the scan and repopulate.
                await pilot.press("r")
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.deps_cache is not None, "`r` did not repopulate deps_cache"
                assert deps.calls > first, "`r` did not call data.dependencies again"
                assert "langchain-core" in _pane_text(app), "dep rows did not render after r"

    _run(go())


def test_r_scans_on_guard():
    guard = _Stub(_GUARD)

    async def go():
        app = MissionControlApp(demo=True)
        with _patch(guard=guard):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("4")  # guard
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.tab == "guard"
                assert app.state.guard_cache is not None, "auto-load did not populate guard_cache"
                first = guard.calls

                app.state = app.state.with_(guard_cache=None)
                await app._render_pane()
                await pilot.pause()
                txt = _pane_text(app)
                assert "No guard run yet" in txt, txt
                assert "adoption firewall" in txt, txt

                await pilot.press("r")
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.guard_cache is not None, "`r` did not repopulate guard_cache"
                assert guard.calls > first, "`r` did not call data.guard again"

    _run(go())


def test_r_loads_on_settings():
    pol = _Stub(_POLICY)
    prof = _Stub(_PROFILE)
    doc = _Stub(_DOCTOR)

    async def go():
        app = MissionControlApp(demo=True)
        with _patch(policy=pol, repo_profile=prof, doctor=doc):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("8")  # settings
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.tab == "settings"
                assert app.state.settings_cache is not None, "auto-load did not populate settings_cache"
                first_doc, first_pol, first_prof = doc.calls, pol.calls, prof.calls

                app.state = app.state.with_(settings_cache=None)
                await app._render_pane()
                await pilot.pause()
                txt = _pane_text(app)
                assert "to load policy" in txt, txt

                await pilot.press("r")
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.settings_cache is not None, "`r` did not repopulate settings_cache"
                assert doc.calls > first_doc, "`r` did not re-run the doctor loader"
                assert pol.calls > first_pol, "`r` did not re-run the policy loader"
                assert prof.calls > first_prof, "`r` did not re-run the repo_profile loader"

    _run(go())
