"""Mouse↔keyboard parity: a click runs the SAME action a key does (handoff §5).

The click callback stored on each ``ClickStatic``/``LineClickStatic`` is exactly
what Textual invokes on a real ``events.Click``; calling it directly is a
faithful, deterministic stand-in for a click in a headless test.
"""

import asyncio

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.widgets import ClickStatic


def _run(coro):
    return asyncio.run(coro)


def _find_click(app, widget_id):
    for w in app.query(ClickStatic):
        if getattr(w, "id", "") == widget_id:
            return w
    raise AssertionError(f"no ClickStatic with id {widget_id!r}")


def test_clicking_deps_scan_button_runs_scan():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.press("6")  # deps tab
            await pilot.pause()
            app.state = app.state.with_(deps_cache=None)
            await app._render_pane()
            await pilot.pause()
            btn = _find_click(app, "cap-scan-deps")
            btn._on_click_cb()  # exactly what a real click invokes
            for _ in range(40):
                await asyncio.sleep(0.05)
                if app.state.deps_cache is not None:
                    break
            assert app.state.deps_cache is not None, "click did not run the deps scan"

    _run(go())


def test_clicking_guard_scan_button_runs_scan():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.press("4")  # guard tab
            await pilot.pause()
            app.state = app.state.with_(guard_cache=None)
            await app._render_pane()
            await pilot.pause()
            _find_click(app, "cap-scan-guard")._on_click_cb()
            for _ in range(40):
                await asyncio.sleep(0.05)
                if app.state.guard_cache is not None:
                    break
            assert app.state.guard_cache is not None, "click did not run the guard scan"

    _run(go())


def test_clicking_settings_load_button_loads():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.press("8")  # settings tab
            await pilot.pause()
            app.state = app.state.with_(settings_cache=None)
            await app._render_pane()
            await pilot.pause()
            _find_click(app, "cap-scan-settings")._on_click_cb()
            for _ in range(40):
                await asyncio.sleep(0.05)
                if app.state.settings_cache is not None:
                    break
            assert app.state.settings_cache is not None, "click did not load settings"

    _run(go())
