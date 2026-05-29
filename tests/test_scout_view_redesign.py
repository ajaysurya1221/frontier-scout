"""v1.3.0 Stream C — Scout view affordances.

Pin the user-facing wins of the redesign:

- No auto-fire on mount: the verdicts table is empty until the user
  explicitly presses ▶ Scout now (or `s`). This kills the "stuck
  screen" UX that v1.2.1 shipped with.
- ▶ Scout now button exists, is the focused widget on mount so Enter
  triggers a scout immediately.
- Lab / Evaluate / Dossier exist as visible buttons (not just
  bindings) so newcomers can discover them.
- DataTable has a Concerns column whose chip colour reflects the
  highest-severity concern present.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed(path: Path) -> Path:
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    return path


def test_scout_view_does_not_auto_fire_on_mount(tmp_path, monkeypatch):
    """v1.2.1 ran the worker in on_mount, leaving the detail panel
    stuck on "Scouting your repo…". v1.3.0 — no auto-fire."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from textual.widgets import DataTable

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            # No internal row cache → the worker hasn't run yet.
            assert scout._rows == []
            # The verdict table is empty.
            table = scout.query_one("#scout-table", DataTable)
            assert table.row_count == 0

    asyncio.run(run())


def test_scout_run_button_uses_success_variant(tmp_path, monkeypatch):
    """▶ Scout now uses the success variant so it visually advertises
    as the primary action without grabbing focus (we don't focus it
    on mount because doing so forcibly activates the Scout pane,
    breaking `--tab settings` on launch — see scout_tab.on_mount)."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from textual.widgets import Button

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            run_btn = app.query_one("#scout-run", Button)
            assert run_btn.variant == "success"
            assert "Scout now" in str(run_btn.label)

    asyncio.run(run())


def test_action_buttons_for_lab_evaluate_dossier_are_visible(tmp_path, monkeypatch):
    """Every binding has a button so they're discoverable."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from textual.widgets import Button

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            for btn_id in ("#scout-lab", "#scout-evaluate", "#scout-dossier"):
                btn = app.query_one(btn_id, Button)
                assert btn is not None

    asyncio.run(run())


def test_run_button_triggers_scout_worker(tmp_path, monkeypatch):
    """Clicking ▶ Scout now should populate the verdict table."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from textual.widgets import DataTable

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#scout-run")
            # The @work(thread=True) worker calls back into the main
            # loop; give Textual a tick or two to drain the queue.
            for _ in range(40):
                await pilot.pause()
                scout = app.query_one(ScoutTab)
                if scout._rows:
                    break
                await asyncio.sleep(0.05)
            scout = app.query_one(ScoutTab)
            assert scout._rows, "▶ Scout now should populate verdicts"
            table = scout.query_one("#scout-table", DataTable)
            assert table.row_count == len(scout._rows)

    asyncio.run(run())


def test_concerns_column_chip_uses_severity_colour():
    """``_concerns_cell`` picks the highest-severity colour."""

    from frontier_scout.tui.tabs.scout_tab import ScoutTab

    # Build a thin instance to call the helper. We can't fully mount
    # without setting up an app; the helper is a pure method on rows.
    class _Stub:
        pass

    stub = _Stub()
    stub._concerns_cell = ScoutTab._concerns_cell.__get__(stub)  # type: ignore[attr-defined]

    high = stub._concerns_cell(
        {"raw": {"concerns": [{"severity": "high"}, {"severity": "low"}]}}
    )
    med = stub._concerns_cell(
        {"raw": {"concerns": [{"severity": "medium"}, {"severity": "low"}]}}
    )
    low = stub._concerns_cell({"raw": {"concerns": [{"severity": "low"}]}})
    none = stub._concerns_cell({"raw": {"concerns": []}})
    assert "ff6b6b" in high  # red
    assert "e3c26f" in med  # amber
    assert "7aa6ff" in low  # blue
    assert "6e8aa1" in none  # muted dash
