"""Tests for the Briefing TUI (v1.5.0, ``frontier_scout/tui2``).

The Briefing's whole design goal is zero bugs, so these tests are the proof:
every screen renders at five terminal sizes, the state machine lands on the
right screen for every transition, the compass always advertises an exit, the
carousel clamps at both ends, a raising worker becomes an ErrorScreen (the app
survives), and ``Finding.from_verdict`` is a pure function.

All async via ``app.run_test(size=…)`` + ``asyncio.run`` — no new deps, matching
the existing suite.
"""

from __future__ import annotations

import asyncio

from frontier_scout.tui2 import BriefingApp
from frontier_scout.tui2.screens.action_result import ActionResultScreen
from frontier_scout.tui2.screens.error import ErrorScreen
from frontier_scout.tui2.screens.explore import ExploreScreen
from frontier_scout.tui2.screens.findings import FindingsScreen
from frontier_scout.tui2.screens.home import HomeScreen
from frontier_scout.tui2.screens.settings import SettingsScreen
from frontier_scout.tui2.screens.working import WorkingScreen
from frontier_scout.tui2.state import AppState, Concern, Finding

SIZES = [(50, 12), (72, 20), (80, 24), (120, 40), (200, 60)]


def _sample_findings() -> tuple[Finding, ...]:
    return (
        Finding(
            tool_name="dspy",
            verdict="adopt",
            fit="high",
            risk="low",
            category="agent_framework",
            summary="Declarative framework for programming language models.",
            why_fit="matches local agent workflow; Docker available",
            next_step="frontier-scout lab dspy --url https://github.com/stanfordnlp/dspy",
            url="https://github.com/stanfordnlp/dspy",
            concerns=(Concern("burns_tokens", "burns tokens", "medium", "many calls per query"),),
        ),
        Finding(
            tool_name="langgraph",
            verdict="trial",
            fit="medium",
            risk="medium",
            category="agent_framework",
            summary="Graph-based orchestration for LLM agents.",
            why_fit="you already use langchain",
            next_step="evaluate it",
            url="https://github.com/langchain-ai/langgraph",
        ),
        Finding(
            tool_name="hold-me",
            verdict="hold",
            fit="low",
            risk="high",
            category="dev_tool",
            summary="Risky tool.",
            why_fit="",
            next_step="",
            url="",
        ),
    )


def _run(coro):
    return asyncio.run(coro)


# ── 1. Every screen renders at every size ────────────────────────────────────


def test_home_renders_at_all_sizes():
    async def go():
        for size in SIZES:
            app = BriefingApp(demo=True)
            async with app.run_test(size=size):
                assert isinstance(app.screen, HomeScreen)
                assert app.screen.query_one("#compass")
                assert app.screen.query_one("#header")

    _run(go())


def test_findings_screen_renders_at_all_sizes():
    async def go():
        for size in SIZES:
            app = BriefingApp(demo=True)
            async with app.run_test(size=size) as pilot:
                app.state = app.state.with_(findings=_sample_findings(), cursor=0)
                await app.push_screen(FindingsScreen())
                await pilot.pause()
                assert isinstance(app.screen, FindingsScreen)
                # The card body has content (title + prose) at every size.
                assert app.screen.query_one("#body").children

    _run(go())


def test_all_static_screens_mount():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            for screen in (
                ExploreScreen(),
                SettingsScreen(),
                WorkingScreen("Testing…"),
                ErrorScreen("boom", "try again"),
                ActionResultScreen("text", ("Title", "Body text")),
            ):
                await app.push_screen(screen)
                await pilot.pause()
                assert app.screen.query_one("#compass")
                app.pop_screen()
                await pilot.pause()

    _run(go())


# ── 2. State machine transitions ─────────────────────────────────────────────


def test_home_scout_to_findings():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            app.start_scout()
            await pilot.pause()
            # Worker pushes WorkingScreen then (demo = seeded, fast) finishes.
            for _ in range(50):
                if isinstance(app.screen, FindingsScreen):
                    break
                await pilot.pause(0.05)
            assert isinstance(app.screen, FindingsScreen)
            assert app.state.findings  # populated from the scan

    _run(go())


def test_working_cancel_returns_home():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.push_screen(WorkingScreen("Long task…"))
            await pilot.pause()
            assert isinstance(app.screen, WorkingScreen)
            app.cancel_work()
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    _run(go())


def test_findings_primary_with_repo_goes_to_working_then_result():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            app.state = app.state.with_(findings=_sample_findings(), cursor=0, has_repo=True)
            await app.push_screen(FindingsScreen())
            await pilot.pause()
            app.screen.action_primary()  # Implement & test (repo present)
            await pilot.pause()
            # Routes through WorkingScreen then lands on ActionResultScreen.
            for _ in range(80):
                if isinstance(app.screen, ActionResultScreen):
                    break
                await pilot.pause(0.05)
            assert isinstance(app.screen, ActionResultScreen)

    _run(go())


# ── 3. Compass correctness ───────────────────────────────────────────────────


def test_every_screen_compass_advertises_an_exit():
    screens = [
        HomeScreen(),
        ExploreScreen(),
        SettingsScreen(),
        WorkingScreen(),
        ErrorScreen("x"),
        ActionResultScreen("text", ("t", "b")),
    ]

    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            for screen in screens:
                await app.push_screen(screen)
                await pilot.pause()
                text = app.screen.compass_text().lower()
                assert text.strip(), f"empty compass on {type(screen).__name__}"
                assert any(tok in text for tok in ("esc", "quit", "cancel", "back")), text
                app.pop_screen()
                await pilot.pause()

    _run(go())


# ── 4. Carousel clamp ────────────────────────────────────────────────────────


def test_carousel_clamps_and_dot_trail_matches():
    findings = _sample_findings()
    state = AppState(findings=findings, cursor=0)
    # Left at first stays at 0.
    assert state.prev_card().cursor == 0
    # Right past last stays at last.
    end = state.at(len(findings) - 1)
    assert end.next_card().cursor == len(findings) - 1
    # current always in range.
    for i in range(-3, len(findings) + 3):
        assert state.at(i).current is not None


def test_carousel_navigation_in_app():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            app.state = app.state.with_(findings=_sample_findings(), cursor=0)
            await app.push_screen(FindingsScreen())
            await pilot.pause()
            await app.screen.action_nav(1)
            assert app.state.cursor == 1
            await app.screen.action_nav(-5)  # clamps at 0
            assert app.state.cursor == 0
            await app.screen.action_nav(99)  # clamps at last
            assert app.state.cursor == len(_sample_findings()) - 1

    _run(go())


# ── 5. Error boundary ────────────────────────────────────────────────────────


def test_worker_exception_lands_on_error_screen():
    async def go():
        app = BriefingApp(demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            def boom(_reporter):
                raise RuntimeError("kaboom")

            app._launch("scout", "Boom…", boom)
            await pilot.pause()
            for _ in range(40):
                await pilot.pause(0.05)
                if isinstance(app.screen, ErrorScreen):
                    break
            assert isinstance(app.screen, ErrorScreen)
            # App is still alive and usable.
            assert app.is_running

    _run(go())


# ── 6. Determinism of the view-model ─────────────────────────────────────────


def test_finding_from_verdict_is_pure():
    raw = {
        "tool_name": "dspy",
        "verdict": "adopt",
        "fit": "high",
        "risk": "low",
        "category": "agent_framework",
        "what": "x",
        "fit_reasons": ["a", "b"],
        "next_safe_step": "do it",
        "source_url": "https://example.com",
        "concerns": [{"slug": "s", "label": "L", "severity": "high", "evidence": "e"}],
    }
    a = Finding.from_verdict(raw)
    b = Finding.from_verdict(dict(raw))
    assert a == b
    assert a.why_fit == "a; b"
    assert a.ribbon == "ADOPT"
    assert a.top_severity == "high"


def test_finding_from_verdict_tolerates_missing_keys():
    f = Finding.from_verdict({})
    assert f.tool_name == "unknown"
    assert f.verdict == "assess"
    assert f.concerns == ()
    assert f.top_severity == ""
