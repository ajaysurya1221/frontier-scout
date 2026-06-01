"""Regression tests for the guard-railed action GATES in Mission Control (tui3).

These tests exist to lock down the safety behaviour of every action that can
spend money, mutate the database, install a package, or otherwise touch a real
backend:

    * ``i``  implement     — cost-gated ConfirmScreen, then ``data.implement``
    * ``e``  evaluate      — ConfirmScreen (spends), then ``data.evaluate``
    * ``L``  lab           — ConfirmScreen (PyPI install), then ``data.lab``
    * ``D``  dossier       — FREE, no gate, straight to ``data.dossier``
    * ``X``  clear history — TypedConfirmScreen (token "clear"), ``data.clear_history``
    * ``R``  reconfigure   — ConfirmScreen, then ``self.exit(42)``

EVERY backend call goes through ``frontier_scout.tui3.data`` and the app imports
that module by reference (``from frontier_scout.tui3 import data``), so patching
the module attributes is seen by the running worker. Each test replaces the
relevant ``data`` function with a record-only stub BEFORE the keypress, so even
a fully correct "confirm" path never spends a token, wipes the store, or
installs anything. A stub's ``.calls`` counter and ``.last_kwargs`` let us prove
both that the gate BLOCKS (calls == 0 on cancel/reject) and that the confirm
wire fires exactly once on success — without ever invoking the real, dangerous
code. The patch is restored afterwards so the stubs never leak into other tests.

Async style mirrors ``test_tui3.py`` / ``test_tui3_scout_run.py``: a module-level
``_run`` that drives ``asyncio.run`` over an ``async def go()`` using
``app.run_test(size=...)``.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

from textual.widgets import Input

from frontier_scout.tui3 import data
from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.overlays import (
    ConfirmScreen,
    ResultScreen,
    TypedConfirmScreen,
)
from frontier_scout.tui3.state import Verdict


def _run(coro):
    return asyncio.run(coro)


@contextmanager
def _patch(name, stub):
    """Swap a ``frontier_scout.tui3.data`` attribute for ``stub``, then restore.

    Restoring guarantees these record-only stubs never leak into another test or
    the rest of the suite — the real spend/destructive backend is never left
    reachable behind the patched name once the test is done.
    """
    orig = getattr(data, name)
    setattr(data, name, stub)
    try:
        yield
    finally:
        setattr(data, name, orig)


class _Stub:
    """Record-only stand-in for a ``data`` backend function.

    Never touches a real backend. Counts invocations and remembers the args /
    keyword args of the most recent call so tests can assert the wire fired
    correctly (and only on the path that is supposed to fire it).
    """

    def __init__(self, ret):
        self.ret = ret
        self.calls = 0
        self.last_args = None
        self.last_kwargs = None

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.last_args = args
        self.last_kwargs = kwargs
        return self.ret


def _verdict(**overrides):
    """An actionable verdict (has ``source_url`` so evaluate/lab are enabled)."""
    payload = {
        "tool_name": "ruff",
        "category": "linting",
        "verdict": "adopt",
        "fit": "high",
        "risk": "low",
        "source_url": "https://github.com/astral-sh/ruff",
    }
    payload.update(overrides)
    return Verdict.from_payload(payload)


async def _seed_scout(pilot, app):
    """Move to the Scout tab and select one actionable verdict."""
    await pilot.pause()
    app.state = app.state.with_(tab="scout", verdicts=(_verdict(),), sel=0)
    await pilot.pause()
    assert app.state.tab == "scout"
    assert app.state.current is not None


# ----------------------------------------------------------------------
# 1. Dossier — FREE action, no gate, straight to a ResultScreen.
# ----------------------------------------------------------------------
def test_dossier_opens_result_screen():
    stub = _Stub(
        {
            "tool_name": "ruff",
            "fit": "high",
            "risk": "low",
            "summary": "x",
            "gaps": [],
            "next_step": "y",
            "policy": "",
            "receipt_path": "",
        }
    )

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("dossier", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await _seed_scout(pilot, app)
                await pilot.press("D")
                await pilot.pause()
                await asyncio.sleep(0.6)
                await pilot.pause()
                assert stub.calls == 1, f"dossier stub calls={stub.calls}"
                assert isinstance(app.screen, ResultScreen), app.screen

    _run(go())


# ----------------------------------------------------------------------
# 2. Implement — cost gate. Cancelling must NOT call the backend.
# ----------------------------------------------------------------------
def test_implement_cost_gate_cancel_does_not_call_backend():
    stub = _Stub({})

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("implement", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await _seed_scout(pilot, app)
                await pilot.press("i")
                await pilot.pause()
                assert isinstance(app.screen, ConfirmScreen), app.screen
                await pilot.press("escape")
                await pilot.pause()
                assert len(app.screen_stack) == 1
                assert stub.calls == 0, f"implement called despite cancel: {stub.calls}"

    _run(go())


# ----------------------------------------------------------------------
# 3. Implement — confirming in demo calls the backend with dry_run=True.
#    This proves the demo confirm path is the zero-spend path.
# ----------------------------------------------------------------------
def test_implement_confirm_demo_calls_backend_dry_run():
    stub = _Stub(
        {
            "status": "dry_run",
            "summary": "ok",
            "test_output": "",
            "files": [],
            "diff": "",
        }
    )

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("implement", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await _seed_scout(pilot, app)
                await pilot.press("i")
                await pilot.pause()
                assert isinstance(app.screen, ConfirmScreen), app.screen
                await pilot.press("y")
                await pilot.pause()
                await asyncio.sleep(0.6)
                await pilot.pause()
                assert stub.calls == 1, f"implement stub calls={stub.calls}"
                assert stub.last_kwargs.get("dry_run") is True, stub.last_kwargs

    _run(go())


# ----------------------------------------------------------------------
# 4. Evaluate — gate opens; cancelling must NOT call the backend.
# ----------------------------------------------------------------------
def test_evaluate_gate_opens_and_cancel():
    stub = _Stub({"ok": True, "summary": "x"})

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("evaluate", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await _seed_scout(pilot, app)
                await pilot.press("e")
                await pilot.pause()
                assert isinstance(app.screen, ConfirmScreen), app.screen
                await pilot.press("escape")
                await pilot.pause()
                assert len(app.screen_stack) == 1
                assert stub.calls == 0, f"evaluate called despite cancel: {stub.calls}"

    _run(go())


# ----------------------------------------------------------------------
# 5. Lab — gate opens; cancelling must NOT call the backend.
# ----------------------------------------------------------------------
def test_lab_gate_opens_and_cancel():
    stub = _Stub({"ok": True, "status": "passed"})

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("lab", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await _seed_scout(pilot, app)
                await pilot.press("L")
                await pilot.pause()
                assert isinstance(app.screen, ConfirmScreen), app.screen
                await pilot.press("escape")
                await pilot.pause()
                assert len(app.screen_stack) == 1
                assert stub.calls == 0, f"lab called despite cancel: {stub.calls}"

    _run(go())


# ----------------------------------------------------------------------
# 6. Clear history — typed gate must REJECT a wrong token (never fire).
# ----------------------------------------------------------------------
def test_clear_history_typed_gate_rejects_wrong_token():
    stub = _Stub(0)

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("clear_history", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("8")  # settings tab
                await pilot.pause()
                assert app.state.tab == "settings"
                await pilot.press("X")
                await pilot.pause()
                assert isinstance(app.screen, TypedConfirmScreen), app.screen
                # Type the WRONG token and submit it.
                inp = app.screen.query_one(Input)
                inp.value = "nope"
                await pilot.pause()
                inp.post_message(Input.Submitted(inp, "nope"))
                await pilot.pause()
                await asyncio.sleep(0.2)
                await pilot.pause()
                # Wrong token: backend never fired and the modal is still up
                # (not dismissed back to the base dashboard).
                assert stub.calls == 0, f"clear_history fired on wrong token: {stub.calls}"
                assert isinstance(app.screen, TypedConfirmScreen), app.screen
                assert len(app.screen_stack) == 2
                # Bail out — still must never have fired.
                await pilot.press("escape")
                await pilot.pause()
                assert stub.calls == 0, f"clear_history fired after escape: {stub.calls}"

    _run(go())


# ----------------------------------------------------------------------
# 7. Clear history — the CORRECT token fires the (stubbed) backend once.
#    The stub does NOT touch the real DB, so this is safe.
# ----------------------------------------------------------------------
def test_clear_history_correct_token_fires_stub():
    stub = _Stub(0)

    async def go():
        app = MissionControlApp(demo=True)
        with _patch("clear_history", stub):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("8")  # settings tab
                await pilot.pause()
                assert app.state.tab == "settings"
                await pilot.press("X")
                await pilot.pause()
                assert isinstance(app.screen, TypedConfirmScreen), app.screen
                inp = app.screen.query_one(Input)
                inp.value = "clear"
                await pilot.pause()
                inp.post_message(Input.Submitted(inp, "clear"))
                await pilot.pause()
                await asyncio.sleep(0.3)
                await pilot.pause()
                assert stub.calls == 1, f"clear_history stub calls={stub.calls}"

    _run(go())


# ----------------------------------------------------------------------
# 8. Reconfigure — confirming must exit with code 42 (relaunch wizard).
# ----------------------------------------------------------------------
def test_reconfigure_confirm_exits_42():
    recorded = []

    async def go():
        app = MissionControlApp(demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("8")  # settings tab
            await pilot.pause()
            assert app.state.tab == "settings"
            # Patch exit so confirming records the code instead of tearing the
            # test harness down mid-run.
            app.exit = lambda code=0: recorded.append(code)
            await pilot.press("R")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen), app.screen
            # Drive the confirm directly so the patched exit is what runs.
            app.screen.action_confirm()
            await pilot.pause()
            assert recorded == [42], recorded

    _run(go())
