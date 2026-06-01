"""Anti-bug regressions (handoff §6 / §10): first-paint never floors, no
DuplicateIds under churn, u/c re-render everything, reflow to the floor and
back, and modals are visible on the first frame."""

import asyncio

from textual.geometry import Size

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.kit import breakpoint_for
from frontier_scout.tui3.overlays import RepoSwitcherScreen


def _run(coro):
    return asyncio.run(coro)


class _ZeroSizeApp(MissionControlApp):
    """An app whose container reports a not-yet-laid-out (0×0) size."""

    @property
    def size(self) -> Size:
        return Size(0, 0)


def test_term_size_falls_back_when_unlaid_out():
    app = _ZeroSizeApp(demo=True)
    app._size_override = None
    cols, rows = app._term_size
    assert breakpoint_for(cols, rows).name != "tiny", "first paint collapsed to the floor"


def test_first_paint_normal_terminal_no_floor():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app._bp_name != "tiny"

    _run(go())


def test_no_duplicate_ids_after_churn():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            for _ in range(5):
                await pilot.press("6")
                await pilot.press("r")
                await pilot.pause()
                await pilot.press("p")
                await pilot.press("escape")
                await pilot.pause()
                await pilot.press("1")
                await pilot.press("4")
                await pilot.pause()
            # Reaching here without a raised DuplicateIds is the assertion.
            assert list(app.query("#mc-main"))

    _run(go())


def test_u_and_c_rerender_everything():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            u0, c0 = app.state.unicode, app.state.color
            await pilot.press("u")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.state.unicode != u0, "u did not toggle unicode"
            assert app.state.color != c0, "c did not toggle color"
            assert list(app.query("#mc-main")), "panes did not re-render after u/c"

    _run(go())


def test_reflow_through_every_breakpoint_and_back():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            seen = set()
            for w, h in [(160, 50), (110, 34), (80, 24), (56, 20), (34, 10), (160, 50)]:
                await pilot.resize_terminal(w, h)
                await pilot.pause()
                seen.add(app._bp_name)
            assert "tiny" in seen and "wide" in seen, f"breakpoints not exercised: {seen}"

    _run(go())


def test_repo_switcher_visible_on_first_frame():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert isinstance(app.screen, RepoSwitcherScreen)
            # Content is mounted (painted) on the first frame — not gated on a
            # transition/animation (handoff Bug #4).
            assert list(app.screen.query("#repo-list")), "modal content not present on frame 1"

    _run(go())
