"""Regression: pressing ``s`` must run a scout without crashing (tui3).

This guards a real defect: ``_scout_worker`` originally used Textual's ``@work``
decorator on a zero-argument nested function. ``@work`` assumes the wrapped
callable is a method (``self = args[0]``), so invoking it raised
``IndexError: tuple index out of range`` the moment the user pressed ``s``. No
other test pressed ``s``, so it slipped through. The fix calls
``run_worker(thread=True)`` directly; this test presses ``s`` end-to-end so the
crash can never come back.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui3.app import MissionControlApp


def _run(coro):
    return asyncio.run(coro)


def test_pressing_s_runs_scout_without_crashing():
    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("s")  # the line that used to raise IndexError
            await pilot.pause()
            await pilot.pause()
            # Demo/dry-run scan completes on the worker thread; give it a beat.
            await asyncio.sleep(1.0)
            await pilot.pause()
            # The app survived and the scan settled (demo data populates verdicts).
            assert app._scanning is False
            assert len(app.state.verdicts) > 0

    _run(go())


def test_pressing_r_refreshes_capability_tabs_without_crashing():
    """The same run_worker path backs the guard/deps refresh (``r``)."""

    async def go():
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("4")  # guard tab
            await pilot.pause()
            await pilot.press("r")  # refresh — worker, off the render path
            await pilot.pause()
            await asyncio.sleep(0.5)
            await pilot.pause()
            assert app.state.guard_cache is not None  # worker populated the cache
            await pilot.press("6")  # deps tab
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            await asyncio.sleep(0.5)
            await pilot.pause()
            assert app.state.deps_cache is not None

    _run(go())
