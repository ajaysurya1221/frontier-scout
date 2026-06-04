"""Golden-frame test for the scan-progress surface (v6 §1).

``scan_progress_lines`` is a width-parameterized pure function reproducing the
golden "SCAN STATE" frame (``ascii_golden_frames.txt``): a spinner frame + a
fixed-width radar sweep, a 5-stage done/active/todo checklist, and a footer.
Markers degrade to ascii v / > / o; the sweep is exactly ``width`` cells.
"""

from __future__ import annotations

import re

from frontier_scout.tui3.kit import asciify, cell_width
from frontier_scout.tui3.scout_view import scan_progress_lines


def _plain(line, unicode=True):
    s = re.sub(r"\[/?[^\]]*\]", "", line)
    return s if unicode else asciify(s)


def test_scan_progress_matches_golden_ascii():
    # Golden frame: stage 2 ("judge fit") active, head at col 7, spinner frame "/".
    lines = scan_progress_lines(
        "checkout-service", stage=2, head=7, frame_idx=1, motion=True, unicode=False
    )
    plain = [_plain(ln, unicode=False) for ln in lines]
    assert plain[0] == "/ scanning   -----++#--------------"
    assert plain[1] == "  v read tree"
    assert plain[2] == "  v parse symbols"
    assert plain[3] == "  > judge fit ..."
    assert plain[4] == "  o score risk"
    assert plain[5] == "  o rank"
    assert "reading checkout-service" in plain[6]
    assert "offline pass" in plain[6]
    assert "nothing leaves your machine" in plain[6]


def test_scan_sweep_width_invariant_both_modes():
    # The sweep run is exactly `width` cells at every head position, in both glyph
    # sets — the anti-drift guarantee for the scanning line.
    for uni in (True, False):
        for head in range(0, 22):
            lines = scan_progress_lines(
                "r", stage=2, head=head, frame_idx=0, motion=True, unicode=uni, width=22
            )
            tail = _plain(lines[0], unicode=uni).split("scanning", 1)[1]  # "   " + sweep
            assert cell_width(tail) == 3 + 22, (uni, head, cell_width(tail))


def test_scan_motion_off_holds_frame0_and_static_sweep():
    # Motion off → spinner holds frame 0 (ascii "|") and the sweep is a single
    # static lit pip (no travelling "++#" tail) — still exactly `width` cells.
    lines = scan_progress_lines(
        "r", stage=2, head=9, frame_idx=5, motion=False, unicode=False, width=22
    )
    p0 = _plain(lines[0], unicode=False)
    assert p0.startswith("| scanning")          # frame 0, not frame_idx 5
    assert "++" not in p0                        # no moving tail when static
    tail = p0.split("scanning", 1)[1]
    assert cell_width(tail) == 3 + 22


def test_scan_stage_states_progress():
    # done before the active stage, todo after — the checklist reflects position.
    lines = scan_progress_lines("r", stage=0, head=0, unicode=False)
    plain = [_plain(ln, unicode=False) for ln in lines]
    assert plain[1].startswith("  > ")          # stage 0 active
    assert plain[2].startswith("  o ")          # stage 1 todo
    assert plain[5].startswith("  o ")          # last stage todo
