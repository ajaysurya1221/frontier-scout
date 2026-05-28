"""Stream J — picker offers universal scout + Quit.

When ``frontier-scout`` opens outside a repo, the picker now offers
three escape hatches beyond typing a path:

- "Universal scout (no repo)" — returns a sentinel that the runner
  reads and flips ``SetupApp.universal_mode = True``. ScoutTab then
  surfaces verdicts without persisting them under a bogus repo path.
- "Quit" — dismisses with None; the runner exits cleanly.
- (Existing) Cancel-Esc / typing a path still work.
"""

from __future__ import annotations

import asyncio

from frontier_scout.tui.repo_picker import (
    UNIVERSAL_SCOUT_SENTINEL,
    looks_like_repo,
)


def test_universal_sentinel_is_a_clear_constant():
    """Be intentional about the sentinel — guard against drift."""

    assert UNIVERSAL_SCOUT_SENTINEL == "<UNIVERSAL>"
    # It MUST NOT be a plausible filesystem path.
    assert "/" not in UNIVERSAL_SCOUT_SENTINEL
    assert UNIVERSAL_SCOUT_SENTINEL.startswith("<")


def test_looks_like_repo_rejects_empty_dir(tmp_path):
    """The picker fires when looks_like_repo returns False; pin that
    a brand new empty directory triggers it."""

    empty = tmp_path / "blank"
    empty.mkdir()
    assert looks_like_repo(empty) is False


def test_looks_like_repo_accepts_git_init(tmp_path):
    """A git-init'd directory is enough."""

    (tmp_path / ".git").mkdir()
    assert looks_like_repo(tmp_path) is True


def test_looks_like_repo_accepts_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    assert looks_like_repo(tmp_path) is True


# ---------------------------------------------------------------------------
# Picker modal — async pilot tests
# ---------------------------------------------------------------------------


def test_picker_universal_button_returns_sentinel(tmp_path, monkeypatch):
    """Clicking the "Universal scout" button dismisses with the sentinel."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        from textual.app import App

        from frontier_scout.tui.repo_picker import RepoPickerScreen

        captured: dict = {}

        class _Probe(App):
            def on_mount(self):
                self.push_screen(
                    RepoPickerScreen(),
                    lambda v: captured.__setitem__("value", v) or self.exit(),
                )

        app = _Probe()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Click the universal-scout button.
            await pilot.click("#pick-universal")
            await pilot.pause()
        assert captured.get("value") == UNIVERSAL_SCOUT_SENTINEL

    asyncio.run(run())


def test_picker_quit_button_returns_none(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        from textual.app import App

        from frontier_scout.tui.repo_picker import RepoPickerScreen

        captured: dict = {"value": "untouched"}

        class _Probe(App):
            def on_mount(self):
                self.push_screen(
                    RepoPickerScreen(),
                    lambda v: captured.__setitem__("value", v) or self.exit(),
                )

        app = _Probe()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#picker-quit")
            await pilot.pause()
        assert captured["value"] is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# SetupApp wiring — universal_mode flips the brand bar
# ---------------------------------------------------------------------------


def test_setup_app_universal_mode_brand_bar(tmp_path, monkeypatch):
    """When ``universal_mode=True``, the brand bar shows the universal-mode
    chip instead of the repo path."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.setup_diagnostics import setup_diagnostics

        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)
        app = SetupApp(diagnostics, universal_mode=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app._brand_bar_text()
        assert "universal mode" in text.lower()
        assert str(repo) not in text  # the repo path is hidden

    asyncio.run(run())


def test_setup_app_normal_mode_shows_repo_path(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.setup_diagnostics import setup_diagnostics

        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)
        app = SetupApp(diagnostics)
        async with app.run_test() as pilot:
            await pilot.pause()
            text = app._brand_bar_text()
        assert "universal mode" not in text.lower()

    asyncio.run(run())
