"""Snapshot convergence harness for Mission Control (tui3) — LOCAL ONLY.

CI skips this file (conftest.py ``pytest_ignore_collect`` guard; requires
``pytest-textual-snapshot`` loaded via ``-p pytest_textual_snapshot``).

Run locally to seed or verify:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
        /opt/miniconda3/bin/python -m pytest -p pytest_textual_snapshot \\
        tests/test_tui3_snapshots.py --snapshot-update -q   # seed
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\
        /opt/miniconda3/bin/python -m pytest -p pytest_textual_snapshot \\
        tests/test_tui3_snapshots.py -q                     # verify
"""

from __future__ import annotations

import pytest

from frontier_scout.tui3.app import MissionControlApp
from frontier_scout.tui3.state import Verdict

# Fixed verdict set — deterministic, one per tier, spans all three Scout views
# (matrix shows in wide, tier ledger in mid/narrow). Payloads are minimal but
# satisfy all required Verdict fields (from_payload fills in the rest).
_VERDS = tuple(
    Verdict.from_payload(p)
    for p in [
        {
            "tool_name": "skills",
            "verdict": "adopt",
            "fit": "high",
            "risk": "low",
            "summary": "x",
        },
        {
            "tool_name": "langchain",
            "verdict": "trial",
            "fit": "medium",
            "risk": "medium",
            "summary": "x",
        },
        {
            "tool_name": "autogpt",
            "verdict": "hold",
            "fit": "low",
            "risk": "high",
            "summary": "x",
        },
    ]
)


async def _seed(pilot) -> None:
    """Inject a fixed verdict set so the Scout renders a populated, deterministic
    state (no live scan, no empty matrix). Called by snap_compare's run_before
    after the app is fully mounted but before the screenshot is taken."""
    pilot.app.state = pilot.app.state.with_(verdicts=_VERDS, sel=0)
    await pilot.app._render_pane()
    await pilot.pause()


@pytest.mark.parametrize("size", [(140, 38), (100, 28), (72, 20)])
def test_scout_layout_snapshot(snap_compare, size):
    """Snapshot the Scout tab at wide / mid / narrow terminal sizes.

    The wide size (140×38) shows the Adoption Matrix column; mid (100×28) shows
    the Tier Ledger; narrow (72×20) shows the compact single-column layout.
    All three are parameterized so a width regression at any breakpoint fails.
    """
    assert snap_compare(MissionControlApp(demo=True), terminal_size=size, run_before=_seed)
