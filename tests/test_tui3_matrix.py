"""TDD tests for the Adoption Matrix bucketing + Tier Ledger helpers.

Tests are written first (failing) — then the implementation is added to
scout_view.py.  The helpers are pure/deterministic and carry no Textual
dependency so they can be imported and exercised in isolation.

Coverage:
  1. bucket_matrix — verdicts land in the right (fit, risk) cells with their
     original indices preserved.
  2. ADOPT/HOLD corner placement.
  3. Multiple verdicts per cell; correct indices.
  4. Overflow cap — +N past 14 dots.
  5. tier_ledger — count, fill cap at 8, first-5 + overflow.
  6. tier_ledger — empty tier produces fill=0 and no names.
  7. tier_ledger — all four tiers present in output.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui3.scout_view import bucket_matrix, tier_ledger
from frontier_scout.tui3.state import Verdict

# ── Helpers ──────────────────────────────────────────────────────────────────

def _v(name: str, verdict: str, fit: str, risk: str) -> Verdict:
    return Verdict.from_payload({
        "tool_name": name,
        "verdict": verdict,
        "fit": fit,
        "risk": risk,
    })


# ── 1. bucket_matrix: basic placement ────────────────────────────────────────

def test_bucket_matrix_adopt_lands_top_left():
    """ADOPT: high fit / low risk → cell ("high", "low")."""
    verdicts = (_v("tool-a", "adopt", "high", "low"),)
    cells = bucket_matrix(verdicts)
    assert ("high", "low") in cells
    cell = cells[("high", "low")]
    assert len(cell) == 1
    assert cell[0] == (0, verdicts[0])


def test_bucket_matrix_hold_lands_bottom_right():
    """HOLD: low fit / high risk → cell ("low", "high")."""
    verdicts = (_v("tool-z", "hold", "low", "high"),)
    cells = bucket_matrix(verdicts)
    cell = cells[("low", "high")]
    assert len(cell) == 1
    assert cell[0] == (0, verdicts[0])


def test_bucket_matrix_medium_medium():
    """Medium fit / medium risk lands in the center cell."""
    verdicts = (_v("mid-tool", "trial", "medium", "medium"),)
    cells = bucket_matrix(verdicts)
    cell = cells[("medium", "medium")]
    assert len(cell) == 1
    assert cell[0][0] == 0  # original index


def test_bucket_matrix_preserves_original_indices():
    """Indices refer to positions in the *original* verdicts tuple."""
    verdicts = (
        _v("a", "adopt", "high", "low"),    # index 0
        _v("b", "trial", "medium", "medium"),  # index 1
        _v("c", "hold", "low", "high"),     # index 2
    )
    cells = bucket_matrix(verdicts)
    assert cells[("high", "low")][0][0] == 0
    assert cells[("medium", "medium")][0][0] == 1
    assert cells[("low", "high")][0][0] == 2


def test_bucket_matrix_multiple_verdicts_same_cell():
    """Two verdicts with the same (fit, risk) both land in the same cell."""
    verdicts = (
        _v("a", "adopt", "high", "low"),   # index 0
        _v("b", "adopt", "high", "low"),   # index 1
    )
    cells = bucket_matrix(verdicts)
    cell = cells[("high", "low")]
    assert len(cell) == 2
    indices = [item[0] for item in cell]
    assert indices == [0, 1]


def test_bucket_matrix_all_nine_cells_present():
    """bucket_matrix always returns all 9 cells (even if empty)."""
    from frontier_scout.tui3.scout_view import FITS, RISKS
    cells = bucket_matrix(())
    for f in FITS:
        for r in RISKS:
            assert (f, r) in cells


def test_bucket_matrix_overflow_dot_count():
    """Overflow: only 14 dots shown; remainder counted as +N."""
    # 17 tools all in the same cell.
    verdicts = tuple(
        _v(f"tool-{i}", "adopt", "high", "low")
        for i in range(17)
    )
    cells = bucket_matrix(verdicts)
    cell = cells[("high", "low")]
    # All 17 items are tracked in the cell.
    assert len(cell) == 17
    # The rendering layer caps display at 14; the remainder is len(cell)-14 = 3.
    displayed = cell[:14]
    overflow = len(cell) - 14
    assert len(displayed) == 14
    assert overflow == 3


# ── 2. tier_ledger ────────────────────────────────────────────────────────────

def test_tier_ledger_all_tiers_present():
    """Output always contains rows for all four tiers."""
    ledger = tier_ledger(())
    tiers = {row["tier"] for row in ledger}
    assert tiers == {"adopt", "trial", "assess", "hold"}


def test_tier_ledger_count_correct():
    """Count matches the number of verdicts for each tier."""
    verdicts = (
        _v("a", "adopt", "high", "low"),
        _v("b", "adopt", "high", "low"),
        _v("c", "trial", "medium", "medium"),
    )
    ledger = tier_ledger(verdicts)
    by_tier = {row["tier"]: row for row in ledger}
    assert by_tier["adopt"]["count"] == 2
    assert by_tier["trial"]["count"] == 1
    assert by_tier["assess"]["count"] == 0
    assert by_tier["hold"]["count"] == 0


def test_tier_ledger_fill_capped_at_8():
    """Fill (gauge value) is capped at 8 even when count > 8."""
    CAP = 8
    verdicts = tuple(
        _v(f"tool-{i}", "adopt", "high", "low")
        for i in range(12)
    )
    ledger = tier_ledger(verdicts)
    adopt_row = next(r for r in ledger if r["tier"] == "adopt")
    assert adopt_row["fill"] == CAP
    assert adopt_row["count"] == 12


def test_tier_ledger_fill_equals_count_when_under_cap():
    """Fill equals count when count <= 8."""
    verdicts = tuple(
        _v(f"tool-{i}", "trial", "medium", "medium")
        for i in range(5)
    )
    ledger = tier_ledger(verdicts)
    trial_row = next(r for r in ledger if r["tier"] == "trial")
    assert trial_row["fill"] == 5
    assert trial_row["count"] == 5


def test_tier_ledger_empty_tier():
    """An empty tier has fill=0 and an empty names list."""
    ledger = tier_ledger(())
    for row in ledger:
        assert row["fill"] == 0
        assert row["count"] == 0
        assert row["names"] == []


def test_tier_ledger_first_5_names():
    """Names list contains at most 5 items (first 5 verdicts)."""
    verdicts = tuple(
        _v(f"tool-{i}", "assess", "medium", "medium")
        for i in range(8)
    )
    ledger = tier_ledger(verdicts)
    assess_row = next(r for r in ledger if r["tier"] == "assess")
    assert len(assess_row["names"]) == 5
    assert assess_row["overflow"] == 3


def test_tier_ledger_overflow_zero_when_5_or_fewer():
    """overflow is 0 when count <= 5."""
    verdicts = tuple(
        _v(f"t-{i}", "hold", "low", "high")
        for i in range(3)
    )
    ledger = tier_ledger(verdicts)
    hold_row = next(r for r in ledger if r["tier"] == "hold")
    assert hold_row["overflow"] == 0
    assert len(hold_row["names"]) == 3


def test_tier_ledger_names_contain_index_and_tool_name():
    """Each name entry carries (index, tool_name) so click-to-select works."""
    verdicts = (
        _v("a", "adopt", "high", "low"),   # index 0
        _v("b", "adopt", "high", "medium"),  # index 1
    )
    ledger = tier_ledger(verdicts)
    adopt_row = next(r for r in ledger if r["tier"] == "adopt")
    assert len(adopt_row["names"]) == 2
    assert adopt_row["names"][0] == (0, "a")
    assert adopt_row["names"][1] == (1, "b")


# ── 3. Render smoke: matrix present at wide, ledger at narrow ─────────────────

def _make_app_with_verdicts():
    from frontier_scout.tui3.app import MissionControlApp
    app = MissionControlApp(repo=Path("."), demo=True)
    return app


def _sample_matrix_verdicts() -> tuple[Verdict, ...]:
    return (
        _v("skills", "adopt", "high", "low"),
        _v("cursor", "trial", "medium", "medium"),
        _v("notdiamond", "assess", "low", "low"),
        _v("devin", "hold", "low", "high"),
        _v("ruff", "adopt", "high", "medium"),
    )


def test_matrix_smoke_wide_no_crash():
    """Wide layout renders the matrix without crashing."""
    async def go():
        from frontier_scout.tui3.app import MissionControlApp
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(130, 44)) as pilot:
            app.state = app.state.with_(
                verdicts=_sample_matrix_verdicts(), tab="scout", sel=0
            )
            await pilot.press("1")
            await pilot.pause()
            # The app survived the render without raising.
            assert app.query_one("#mc-main")

    asyncio.run(go())


def test_ledger_smoke_narrow_no_crash():
    """Narrow layout renders the tier ledger without crashing."""
    async def go():
        from frontier_scout.tui3.app import MissionControlApp
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(78, 28)) as pilot:
            app.state = app.state.with_(
                verdicts=_sample_matrix_verdicts(), tab="scout", sel=0
            )
            await pilot.press("1")
            await pilot.pause()
            assert app.query_one("#mc-main")

    asyncio.run(go())


def test_matrix_click_select_updates_state():
    """Clicking a matrix dot updates app.state.sel (click-to-select parity)."""
    async def go():
        from frontier_scout.tui3.app import MissionControlApp
        app = MissionControlApp(repo=Path("."), demo=True)
        async with app.run_test(size=(130, 44)) as pilot:
            verdicts = _sample_matrix_verdicts()
            app.state = app.state.with_(
                verdicts=verdicts, tab="scout", sel=0
            )
            await pilot.press("1")
            await pilot.pause()
            # Programmatically exercise the selection path (same as click callback).
            app._select(2)
            await pilot.pause()
            assert app.state.sel == 2

    asyncio.run(go())


# ── 4. _cell_markup selected-cell corner lock frame ───────────────────────────

def test_cell_markup_frames_selected_cell():
    """Selected cell gets corner glyphs; unselected cell does not."""
    from frontier_scout.tui3 import scout_view
    from frontier_scout.tui3.kit import asciify, glyphs

    class _FakeState:
        unicode = True

    class _FakeApp:
        state = _FakeState()

        def _paint(self, m: str) -> str:
            return m

    v = _v("x", "adopt", "high", "low")
    items = [(0, v)]
    gl = glyphs(True)

    # Cell holds the selected verdict (sel=0 is among item indices).
    md = scout_view._cell_markup(_FakeApp(), gl, items, 0, "high", "low")
    assert gl["corner_tl"] in md, "corner_tl missing in selected cell"
    assert gl["corner_br"] in md, "corner_br missing in selected cell"
    # ASCII degradation: asciify(md) must contain at least two '+' from the corners.
    assert asciify(md).count("+") >= 2, "ASCII corners (+) missing after asciify"

    # Cell does NOT hold the selection (sel=1 is not in items).
    md2 = scout_view._cell_markup(_FakeApp(), gl, items, 1, "high", "low")
    assert gl["corner_tl"] not in md2, "corner_tl must not appear in unselected cell"
    assert gl["corner_br"] not in md2, "corner_br must not appear in unselected cell"


def test_cell_markup_danger_corner_uses_red():
    """Danger corner (fit=low, risk=high) frames selected cell in red."""
    from frontier_scout.tui3 import scout_view
    from frontier_scout.tui3.kit import glyphs

    class _FakeState:
        unicode = True

    class _FakeApp:
        state = _FakeState()

        def _paint(self, m: str) -> str:
            return m

    v = _v("dangerous", "hold", "low", "high")
    items = [(0, v)]
    gl = glyphs(True)

    md = scout_view._cell_markup(_FakeApp(), gl, items, 0, "low", "high")
    red_hex = "#ff6b6b"
    assert gl["corner_tl"] in md, "corner_tl missing in danger selected cell"
    assert red_hex in md, f"danger corner frame should use red ({red_hex})"


def test_cell_markup_normal_corner_uses_mint():
    """Normal selected cell (not danger corner) frames in mint."""
    from frontier_scout.tui3 import scout_view
    from frontier_scout.tui3.kit import glyphs

    class _FakeState:
        unicode = True

    class _FakeApp:
        state = _FakeState()

        def _paint(self, m: str) -> str:
            return m

    v = _v("good", "adopt", "high", "low")
    items = [(0, v)]
    gl = glyphs(True)

    md = scout_view._cell_markup(_FakeApp(), gl, items, 0, "high", "low")
    mint_hex = "#24d6a8"
    assert gl["corner_tl"] in md, "corner_tl missing in selected cell"
    assert mint_hex in md, f"normal corner frame should use mint ({mint_hex})"
