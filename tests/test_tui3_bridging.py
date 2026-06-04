"""Bridging-contract width tests for Mission Control v6 cell-precision.

Consolidates the exact width assertions from
design_handoff_mission_control_v6/BRIDGING_PX_TO_CELLS.md.

These are pure-function unit tests — no Textual, no app — so they run on CI
without any plugin or snapshot machinery.
"""

from __future__ import annotations

import re

from frontier_scout.tui3.kit import asciify, cell_width, glyphs, meter
from frontier_scout.tui3.scout_view import adoption_matrix_lines, bucket_matrix


def test_gauge_width():
    assert len(meter(0.5, 20)) == 22


def test_spark_ascii():
    assert glyphs(False)["spark"] == ".:-=+*#%"


def test_matrix_block_59():
    cells = bucket_matrix(())
    plain = [re.sub(r"\[/?[^\]]*\]", "", ln) for ln in adoption_matrix_lines(cells, -1, 0)]
    grid = [p for p in plain if "|" in p or "│" in p or "+" in p or "─" in p]
    assert grid and all(cell_width(p) == 59 for p in grid)


def test_ramp_folds_ascii():
    assert all(ord(c) < 128 for c in asciify("▁▂▃▄▅▆▇█"))
