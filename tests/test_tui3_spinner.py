from __future__ import annotations
import asyncio
from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.widgets import ScanSpinner


def _run(coro):
    return asyncio.run(coro)


def test_scan_spinner_advances_when_motion_on():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            sp = ScanSpinner("scanning")
            await app.screen.mount(sp)
            await pilot.pause()
            f0 = sp._frame
            sp._tick_frame()
            assert sp._frame != f0
            assert "scanning" in str(sp.content)
    _run(go())


def test_scan_spinner_holds_frame_when_motion_off():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.state = app.state.with_(motion=False, unicode=False)
            sp = ScanSpinner("scanning")
            await app.screen.mount(sp)
            await pilot.pause()
            txt = str(sp.content)
            assert sp._frame == 0
            assert ("|" in txt or "/" in txt or "-" in txt or "\\" in txt)
    _run(go())
