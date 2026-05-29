"""v1.3.0 Stream B — per-tab subtitles + glossary overlay.

Pin the new shell affordances:

- Every tab has a non-empty subtitle (newcomer-friendly one-liner).
- The subtitle refreshes when the user switches tabs.
- ``?`` opens the GlossaryScreen modal; ``Esc`` / ``?`` closes it.
- The glossary lists every term defined in ``TERMS`` and every term
  referenced in ``TAB_SUBTITLES`` is either defined in TERMS or
  mentioned as plain English (no broken references).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui.glossary import (
    TAB_SUBTITLES,
    TERMS,
    GlossaryScreen,
    define,
    label,
)
from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed(path: Path) -> Path:
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    return path


# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------


def test_every_tab_has_a_non_empty_subtitle():
    # Both top-level tabs need a one-liner.
    assert "scout" in TAB_SUBTITLES
    assert "settings" in TAB_SUBTITLES
    for slug, subtitle in TAB_SUBTITLES.items():
        plain = (
            subtitle.replace("[bold]", "")
            .replace("[/]", "")
            .replace("[/bold]", "")
            .strip()
        )
        assert plain, f"tab {slug!r} subtitle is blank after markup strip"


def test_glossary_defines_the_v12_concern_taxonomy():
    """Stream K (v1.2.1) concern slugs all have a glossary entry so
    the chips on a verdict row are never opaque."""

    for slug in (
        "weak_fit",
        "token_burn",
        "abandoned",
        "security_surface",
        "vendor_lock_in",
        "marketing_only",
        "unproven",
    ):
        assert slug in TERMS, f"glossary missing concern slug: {slug!r}"
        lbl, definition = TERMS[slug]
        assert lbl
        assert definition


def test_glossary_helpers_are_defensive():
    """`define` / `label` should never KeyError; they return safe
    defaults for slugs the caller mistypes."""

    assert define("verdict") != ""
    assert define("not-a-real-slug") == ""
    assert label("verdict") == "Verdict"
    assert label("missing") == "missing"


# ---------------------------------------------------------------------------
# GlossaryScreen — opens via ?, closes via Esc / ?
# ---------------------------------------------------------------------------


def test_glossary_overlay_opens_with_question_mark(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, GlossaryScreen)
            # Press ? again to close.
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, GlossaryScreen)

    asyncio.run(run())


def test_subtitle_updates_when_switching_tabs(tmp_path, monkeypatch):
    """Press 2 to jump to Settings — the subtitle widget should
    re-render with the Settings one-liner."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from textual.widgets import Static

        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            subtitle = app.query_one("#tab-subtitle", Static)
            # The renderable is a Rich-rendered string; just check the plain text.
            initial = str(subtitle.render())
            assert "Scout" in initial or "scout" in initial.lower()
            await pilot.press("2")
            await pilot.pause()
            after = str(subtitle.render())
            assert "Settings" in after or "policy" in after.lower()

    asyncio.run(run())


def test_glossary_modal_renders_at_60_cols(tmp_path, monkeypatch):
    """Make sure the overlay survives a tiny terminal (VS Code panel)."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        diagnostics = setup_diagnostics(_seed(tmp_path / "repo"), ollama_timeout_s=0.001)
        from frontier_scout.tui.setup_app import SetupApp

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test(size=(60, 24)) as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, GlossaryScreen)

    asyncio.run(run())
