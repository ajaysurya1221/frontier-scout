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


# ── data.repo_profile — architecture keys ─────────────────────────────────────


def test_repo_profile_exposes_architecture_keys(tmp_path):
    """data.repo_profile on a real (minimal) repo returns the new arch keys."""
    from frontier_scout.tui3 import data as _data

    # Minimal Python repo: one manifest so build_scout_profile has something to scan.
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\ndependencies = ['fastapi>=0.100']\n"
    )

    result = _data.repo_profile(str(tmp_path))

    # New keys added in Change 2 must be present.
    assert "archetype" in result, "archetype missing from repo_profile"
    assert "ai_categories" in result, "ai_categories missing from repo_profile"
    assert "dependencies" in result, "dependencies missing from repo_profile"
    assert "top_imports" in result, "top_imports missing from repo_profile"
    assert "files_scanned" in result, "files_scanned missing from repo_profile"

    # Legacy keys still present (managers keeps the package_managers→managers mapping).
    assert "languages" in result
    assert "frameworks" in result
    assert "managers" in result
    assert "agent_configs" in result
    assert "risk_flags" in result

    # Types are sane.
    assert isinstance(result["archetype"], str)
    assert isinstance(result["ai_categories"], dict)
    assert isinstance(result["dependencies"], list)
    assert isinstance(result["top_imports"], dict)
    assert isinstance(result["files_scanned"], int)


def test_repo_profile_nonexistent_is_defensive():
    """A nonexistent path never raises: build_scout_profile walks an empty tree
    and yields an empty-valued profile dict (the {} fallback is reserved for an
    actual exception, exercised separately below)."""
    from frontier_scout.tui3 import data as _data

    result = _data.repo_profile("/nonexistent/path/to/repo")
    assert isinstance(result, dict)  # never raises
    assert result.get("archetype", "unknown") == "unknown"
    assert result.get("dependencies") == []
    assert result.get("files_scanned") == 0


def test_repo_profile_returns_empty_on_error(monkeypatch):
    """If profile-building raises, repo_profile swallows it and returns {}."""
    from frontier_scout.tui3 import data as _data

    def _boom(*_a, **_k):
        raise RuntimeError("scan blew up")

    monkeypatch.setattr("frontier_scout.profile.build_scout_profile", _boom)
    assert _data.repo_profile("/any/path") == {}


# ── Settings → Architecture instrument (v5) ───────────────────────────────────

_ARCH_PROFILE = {
    "languages": ["python"],
    "frameworks": ["fastapi"],
    "managers": ["uv"],
    "agent_configs": ["CLAUDE.md"],
    "risk_flags": [],
    "archetype": "web-service",
    "ai_categories": {"llm-sdk": ["anthropic"], "vector-store": ["qdrant"]},
    "dependencies": [
        {"name": "fastapi", "ecosystem": "pypi", "version": "0.110.1", "evidence": 12},
        {"name": "anthropic", "ecosystem": "pypi", "version": ">=0.3", "evidence": 5},
    ],
    "top_imports": {"python": ["fastapi", "anthropic"]},
    "files_scanned": 1234,
}


def _settings_text(profile, size=(130, 40)):
    """Boot, open Settings (auto-load uses stubbed data), return the pane text.

    Stubs the three data functions the settings worker calls so nothing scans
    the real cwd, hits the network, or spends. ``size`` selects the breakpoint
    (wide ≥116 cols → two columns; smaller → the stacked reflow branch).
    """

    async def go():
        app = MissionControlApp(demo=True)
        with _patch(
            repo_profile=_Stub(profile),
            policy=_Stub(_POLICY),
            doctor=_Stub(_DOCTOR),
        ):
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                await pilot.press("8")  # Settings tab → auto-load worker
                await pilot.pause()
                await asyncio.sleep(0.4)
                await pilot.pause()
                assert app.state.settings_cache is not None, "settings did not auto-load"
                return _pane_text(app)

    return _run(go())


def test_settings_renders_architecture_section():
    txt = _settings_text(_ARCH_PROFILE)
    assert "Architecture" in txt, txt
    assert "web-service" in txt  # archetype dial (lit)
    assert "llm-sdk" in txt and "anthropic" in txt  # AI bucket + tool tag
    assert "vector-store" in txt and "qdrant" in txt
    assert "key dependencies" in txt and "fastapi" in txt  # dep + evidence gauge
    assert "top imports" in txt
    assert "1,234" in txt  # files_scanned, formatted


def test_settings_architecture_empty_ai_tooling_note():
    profile = {
        "languages": ["c"],
        "frameworks": [],
        "managers": [],
        "agent_configs": [],
        "risk_flags": [],
        "archetype": "unknown",
        "ai_categories": {},
        "dependencies": [],
        "top_imports": {},
        "files_scanned": 0,
    }
    txt = _settings_text(profile)
    assert "No AI tooling detected" in txt, txt
    assert "universal merit" in txt


def test_settings_architecture_stacked_on_narrow():
    """On a sub-wide width the two columns stack (else branch) and still render."""
    txt = _settings_text(_ARCH_PROFILE, size=(100, 40))  # mid → stacked
    assert "Architecture" in txt, txt
    assert "web-service" in txt
    assert "llm-sdk" in txt and "anthropic" in txt
    assert "key dependencies" in txt and "fastapi" in txt


def test_provider_switcher_first_run_framing():
    """The first-run switcher shows the onboarding title, the --demo escape
    hatch, and a 'fix:' line for an unavailable engine (mounted, so body() runs)."""
    from frontier_scout.tui3.overlays import ProviderSwitcherScreen

    choices = [
        {"id": "anthropic", "label": "Anthropic API", "available": True, "hint": "", "active": True},
        {"id": "openai", "label": "OpenAI API", "available": False, "hint": "set OPENAI_API_KEY", "active": False},
    ]

    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(
                ProviderSwitcherScreen(
                    choices,
                    first_run=True,
                    meta=data.providers(),
                    reason="auto",
                    unicode=app.state.unicode,
                )
            )
            await pilot.pause()
            assert isinstance(app.screen, ProviderSwitcherScreen), app.screen
            # app.query targets the base screen; the modal lives on app.screen.
            parts = []
            for w in app.screen.query("Static"):
                c = getattr(w, "content", None)
                parts.append(str(c) if c else str(getattr(w, "renderable", "")))
            txt = "  ".join(parts)
            assert "Choose your engine" in txt, txt
            assert "--demo" in txt
            assert "fix: set OPENAI_API_KEY" in txt

    _run(go())


def test_cap_tab_shows_spinner_while_scanning():
    from frontier_scout.tui3.widgets import ScanSpinner
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("4")          # Guard
            await pilot.pause()
            app._cap_scanning = "guard"     # simulate worker-in-flight
            app.state = app.state.with_(guard_cache=None)
            await app._render_pane()
            await pilot.pause()
            assert app.query(ScanSpinner), "no ScanSpinner on a scanning cap tab"
    _run(go())


def test_cap_spinner_clears_after_scan_failure():
    from frontier_scout.tui3.widgets import ScanSpinner
    from frontier_scout.tui3.messages import WorkFailed

    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("4")  # Guard
            await pilot.pause()
            app._cap_scanning = "guard"
            app.state = app.state.with_(guard_cache=None)
            await app._render_pane()
            await pilot.pause()
            assert app.query(ScanSpinner)  # spinner up mid-scan
            app.post_message(WorkFailed("guard", "boom"))
            await pilot.pause()
            await pilot.pause()
            assert app._cap_scanning is None, "flag not cleared on failure"
            assert not app.query(ScanSpinner), "spinner stuck after failure"

    _run(go())


def test_matrix_crosshair_tones_selected_axes():
    from frontier_scout.tui3.state import Verdict
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(140, 40)) as pilot:   # wide → matrix
            await pilot.pause()
            v = Verdict.from_payload({"tool_name": "x", "verdict": "adopt", "fit": "high", "risk": "low"})
            app.state = app.state.with_(verdicts=(v,), scope="all", sel=0)
            app._scanning = False
            await app._render_pane(); await pilot.pause()
            # Collect markup only from the axis-label widgets (scout-matrix-axis and
            # the risk-header scout-matrix-cell widgets that are part of the header row).
            axis_parts = []
            for w in app.query(".scout-matrix-axis"):
                c = getattr(w, "content", None)
                if c:
                    axis_parts.append(str(c))
            # Also collect the risk-header cells (the header row's scout-matrix-cell widgets)
            # by looking at all scout-matrix-cell statics and filtering to those that
            # contain only a single label token (no dots/numbers = header cells).
            for w in app.query(".scout-matrix-cell"):
                c = getattr(w, "content", None)
                if c and str(c).count("]") <= 2:  # header cell: one markup tag
                    axis_parts.append(str(c))
            axis_txt = "  ".join(axis_parts)
            # fit_tone(high)=mint (#24d6a8); the "hi " label for fit=high must be bold+toned.
            # risk_tone(low)=mint (#24d6a8); the "low" label for risk=low must be bold+toned.
            assert "#24d6a8 b]hi " in axis_txt or "#24d6a8 b]low" in axis_txt, (
                f"Expected toned+bold axis label in axis widgets, got: {axis_txt!r}"
            )
    _run(go())
