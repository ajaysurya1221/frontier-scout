"""v1.3.0 Stream D — Settings panel subtitles.

Every Settings panel ships with a one-line subtitle so newcomers
know what the panel is for before they read the toggles. The
subtitle markup uses the muted slate colour so it sits visually
below the panel title.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed(path: Path) -> Path:
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    return path


def test_each_settings_panel_has_a_subtitle(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False, initial_tab="settings")
        async with app.run_test() as pilot:
            await pilot.pause()
            subtitles = app.query(".settings-subtitle")
            assert len(subtitles) >= 5  # one per panel
            for w in subtitles:
                rendered = str(w.render())  # type: ignore[union-attr]
                # Each subtitle non-empty after stripping markup tags.
                plain = (
                    rendered.replace("[/]", "").strip()
                )
                assert plain, "settings subtitle is blank"
            # Verify all five panels exist by querying section titles.
            titles = app.query(".settings-title")
            assert len(titles) == 5

    asyncio.run(run())
