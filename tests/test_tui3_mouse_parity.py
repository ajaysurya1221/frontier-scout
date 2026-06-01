"""Mouse↔keyboard parity: a click runs the SAME action a key does (handoff §5).

The click callback stored on each ``ClickStatic``/``LineClickStatic`` is exactly
what Textual invokes on a real ``events.Click``; calling it directly is a
faithful, deterministic stand-in for a click in a headless test.
"""

import asyncio

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.widgets import ClickStatic, LineClickStatic


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


def test_clicking_rail_tab_switches_tab():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:  # wide → rail visible
            await pilot.pause()
            await pilot.click("#rail-guard")
            await pilot.pause()
            assert app.state.tab == "guard", "clicking the rail cell did not switch tab"

    _run(go())


def test_clicking_strip_tab_switches_tab():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(70, 24)) as pilot:  # narrow → tabstrip visible
            await pilot.pause()
            # The strip cell's click callback is exactly what a real click invokes;
            # call it directly (a center-click can fall outside bounds at the
            # narrowest widths). The rail test above proves real pilot.click works.
            app.query_one("#strip-deps", ClickStatic)._on_click_cb()
            await pilot.pause()
            assert app.state.tab == "deps", "strip cell not wired to _goto"

    _run(go())


def test_clicking_scope_chip_changes_scope():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app.query_one("#scope-mcp", ClickStatic)._on_click_cb()
            await pilot.pause()
            assert app.state.scope == "mcp", "scope chip click did not change scope"

    _run(go())


def test_scan_affordance_present_and_select_works():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            assert list(app.query("#scout-scan")), "scout scan affordance missing"
            app._select(0)
            await pilot.pause()
            assert app.state.sel == 0

    _run(go())


def test_gate_cancel_by_click():
    from frontier_scout.tui3.overlays import ConfirmScreen

    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            if not app.state.scoped_verdicts:
                return
            app._select(0)
            await pilot.press("L")  # lab gate
            await pilot.pause()
            if not isinstance(app.screen, ConfirmScreen):
                return  # current verdict not lab-eligible; cancel-click covered elsewhere
            app.screen.query_one("#confirm-no", ClickStatic)._on_click_cb()
            await pilot.pause()
            assert len(app.screen_stack) == 1, "clicking cancel did not close the gate"

    _run(go())


def test_palette_rows_clickable():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            results = app.screen.query_one("#cp-results", LineClickStatic)
            assert results._line_map, "palette result rows are not click-wired"
            results._line_map[0]()  # run the first command via click
            await pilot.pause()
            assert len(app.screen_stack) == 1, "clicking a palette row did not dismiss it"

    _run(go())


def test_select_sched_method():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app._select_sched(2)
            assert app.state.sched_sel == 2

    _run(go())
