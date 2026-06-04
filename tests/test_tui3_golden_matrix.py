"""TDD tests for the Adoption Matrix as a 59-cell box-grid pure function (v6 §2).

``adoption_matrix_lines`` is a width-parameterized pure function that emits the
exact box-drawing grid from the golden frame (``ascii_golden_frames.txt`` →
"ADOPTION MATRIX (wide)"). Every grid line is exactly 59 display cells; multi-cell
ascii glyphs (``(o)`` = 3 cells) are measured with ``cell_width``, never ``len()``.

These tests are written first (failing), then the implementation is added to
scout_view.py. They assert the load-bearing invariants:
  • every grid line is exactly 59 cells (unicode + ascii)
  • the static header / divider rows match the golden character-for-character
  • the selected cell uses ``radar_core`` and pads to 17 cells
  • the crosshair tones the selected axis labels bold
  • the corner-lock is unicode-only (folds to ``+`` in ascii)
"""

from __future__ import annotations

import re

from frontier_scout.tui3.kit import asciify, cell_width, glyphs
from frontier_scout.tui3.scout_view import (
    FITS,
    RISKS,
    adoption_matrix_lines,
    bucket_matrix,
)


def _plain(line, unicode=True):
    s = re.sub(r"\[/?[^\]]*\]", "", line)
    return s if unicode else asciify(s)


def _mk(name, verdict, fit, risk):
    from frontier_scout.tui3.state import Verdict

    return Verdict.from_payload(
        {"tool_name": name, "verdict": verdict, "fit": fit, "risk": risk}
    )


def test_every_grid_line_is_59_cells():
    # Each mode is built natively and measured in its own glyph set: the multi-cell
    # ascii radar_core ("(o)" = 3 cells) is reserved by the width function when
    # unicode=False, so the ascii grid is 59 cells — NOT by asciifying a unicode
    # build (which would widen the selected cell by the 1→3 cell radar_core fold).
    # "Identical widths across modes" = each native build is 59 in its own mode.
    vs = tuple(_mk(f"t{i}", "adopt", "high", "low") for i in range(3))
    cells = bucket_matrix(vs)
    for uni in (True, False):
        lines = adoption_matrix_lines(
            cells, sel=0, total=len(vs), sel_fit="high", sel_risk="low", unicode=uni
        )
        # title + header + 3 dividers + 3 data rows region — the fixed 59-cell grid.
        for line in lines[:8]:
            assert cell_width(_plain(line, unicode=uni)) == 59, (
                uni,
                line,
                cell_width(_plain(line, unicode=uni)),
            )


def test_static_header_and_divider_ascii_match_golden():
    cells = bucket_matrix(())
    lines = adoption_matrix_lines(cells, sel=-1, total=0)
    plain = [_plain(line, unicode=False) for line in lines]
    assert "    |       LOW       |       MED       |      HIGH       |" in plain
    assert "    +-----------------+-----------------+-----------------+" in plain


def test_selected_cell_uses_radar_core_and_pads_to_17():
    vs = tuple(_mk(f"t{i}", "adopt", "high", "low") for i in range(3))  # all HI x LOW
    cells = bucket_matrix(vs)
    # Built natively in ascii so the multi-cell "(o)" is reserved correctly.
    lines = adoption_matrix_lines(
        cells, sel=0, total=3, sel_fit="high", sel_risk="low", unicode=False
    )
    hi_row = next(
        _plain(line, unicode=False)
        for line in lines
        if _plain(line, unicode=False).startswith(" HI ")
    )
    low_cell = hi_row.split("|")[1]  # first data column
    assert low_cell.startswith("(o) ")  # radar_core ascii, 3 cells
    assert cell_width(low_cell) == 17


def test_crosshair_tones_selected_axis_labels_bold():
    vs = (_mk("a", "adopt", "high", "low"),)
    cells = bucket_matrix(vs)
    lines = adoption_matrix_lines(
        cells, sel=0, total=1, sel_fit="high", sel_risk="low"
    )
    from frontier_scout.tui3.kit import _TONE_HEX

    blob = "".join(lines)
    assert f"[{_TONE_HEX['mint']} b]" in blob  # selected hi/low → mint bold


def test_corner_lock_unicode_only():
    vs = (_mk("a", "adopt", "high", "low"),)
    cells = bucket_matrix(vs)
    uni = "".join(adoption_matrix_lines(cells, 0, 1, "high", "low", unicode=True))
    assert glyphs(True)["corner_tl"] in uni  # ⌜ present (unicode)
    asc = "".join(
        _plain(line, unicode=False)
        for line in adoption_matrix_lines(cells, 0, 1, "high", "low", unicode=False)
    )
    assert "⌜" not in asc  # folds to + in ascii


def test_empty_matrix_is_still_a_59_cell_grid():
    cells = bucket_matrix(())
    lines = adoption_matrix_lines(cells, sel=-1, total=0)
    for line in lines[:8]:
        assert cell_width(_plain(line, unicode=False)) == 59, (
            line,
            cell_width(_plain(line, unicode=False)),
        )
    # empty data cells are 17 spaces between bars.
    hi_row = next(
        _plain(line, unicode=False)
        for line in lines
        if _plain(line, unicode=False).startswith(" HI ")
    )
    assert hi_row.split("|")[1] == " " * 17


def test_fit_and_risk_labels_are_present():
    cells = bucket_matrix(())
    lines = adoption_matrix_lines(cells, sel=-1, total=0)
    plain = [_plain(line, unicode=False) for line in lines]
    # fit row labels (4-cell gutter): " HI " / "MED " / " LO ".
    assert any(line.startswith(" HI ") for line in plain)
    assert any(line.startswith("MED ") for line in plain)
    assert any(line.startswith(" LO ") for line in plain)


def test_title_row_carries_total_and_is_59_cells():
    vs = tuple(_mk(f"t{i}", "adopt", "high", "low") for i in range(7))
    cells = bucket_matrix(vs)
    lines = adoption_matrix_lines(cells, sel=0, total=7, sel_fit="high", sel_risk="low")
    title = _plain(lines[0], unicode=False)
    assert title.startswith("ADOPTION MATRIX")
    assert title.rstrip().endswith("7")  # total count, right-aligned
    assert cell_width(title) == 59


def test_axes_use_fits_and_risks_order():
    # Guard against silently transposing the grid: FITS top→bottom, RISKS left→right.
    assert FITS == ("high", "medium", "low")
    assert RISKS == ("low", "medium", "high")


def test_heavy_cell_stays_59_cells():
    # 20 verdicts all routed into ONE cell — exercises the count badge + "+N"
    # overflow + the per-cell dot cap + the cell-aware clip. The 3-item happy-path
    # tests miss this; without the cap the concatenated data row bulged to 76-78
    # cells. Every grid line must stay exactly 59 cells in BOTH glyph sets.
    vs = tuple(_mk(f"t{i}", "hold", "low", "high") for i in range(20))
    cells = bucket_matrix(vs)
    for uni in (True, False):
        gl = glyphs(uni)
        lines = adoption_matrix_lines(
            cells, sel=0, total=20, sel_fit="low", sel_risk="high", unicode=uni
        )
        for line in lines:
            p = _plain(line, unicode=uni)
            if gl["box_v"] in p or gl["box_x"] in p or p.lstrip().startswith("ADOPTION"):
                assert cell_width(p) == 59, (uni, cell_width(p), repr(p))
