"""Repo switcher (handoff §9): data.list_repos adapter, w/palette open, j/k+⏎
select, and an honest re-scout on switch."""

import asyncio
import os

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.overlays import RepoSwitcherScreen


def _run(coro):
    return asyncio.run(coro)


def test_list_repos_includes_current():
    repos = data.list_repos(".")
    assert isinstance(repos, list) and len(repos) >= 1, "must return at least the current repo"
    paths = [r["path"] for r in repos]
    assert os.path.realpath(".") in paths  # canonical (symlink-safe), matches list_repos
    for r in repos:
        assert "name" in r and "path" in r


def test_w_opens_repo_switcher():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            assert isinstance(app.screen, RepoSwitcherScreen)

    _run(go())


def test_switcher_enter_calls_switch_repo():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            calls = []
            app.switch_repo = lambda p: calls.append(p)  # record instead of re-init
            await pilot.press("w")
            await pilot.pause()
            assert isinstance(app.screen, RepoSwitcherScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert calls, "pressing enter in the switcher did not call switch_repo"

    _run(go())


def test_stale_scout_result_ignored_after_switch():
    """A scout result tagged with a different repo (an in-flight scout that
    finished after a repo switch) must not overwrite the current repo's state."""
    from frontier_scout.tui3.messages import WorkDone
    from frontier_scout.tui3.state import Funnel

    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            before = app.state.verdicts
            app.post_message(WorkDone("scout", {
                "repo": "/some/other/repo", "verdicts": (), "funnel": Funnel(), "languages": ()}))
            await pilot.pause()
            assert app.state.verdicts == before, "stale scout result overwrote current state"

    _run(go())


def test_switch_repo_triggers_rescout():
    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            ran = []
            app.run_scout = lambda **kw: ran.append(kw)  # record, don't spawn a worker
            app.switch_repo(app.state.repo)
            await pilot.pause()
            assert ran, "switch_repo did not trigger a scout"

    _run(go())
