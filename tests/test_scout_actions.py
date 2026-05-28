"""Stream M — Scout tab gains lab / evaluate / dossier row actions.

Each binding invokes the same underlying CLI function the user would
otherwise drop to a shell for. The tests stub the heavy callable
(``lab_runner.run``, ``evaluate_url``, ``build_dossier``) so we never
hit the network and don't need an API key.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from frontier_scout.tui.setup_diagnostics import setup_diagnostics


def _seed(path: Path) -> Path:
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi==0.115.0\n")
    return path


def _seed_row(verdict_dict):
    """Mirror ``ScoutTab._ai_verdict_to_row`` — the ``raw`` payload
    must include ``source_url`` because the action handlers read it
    from ``row["raw"]``, not from the row dict's top level."""

    enriched = dict(verdict_dict)
    enriched.setdefault("source_url", "https://github.com/fake/tool")
    enriched.setdefault("tool_name", "fake/tool")
    return {
        "kind": "ai",
        "verdict": str(enriched.get("verdict", "trial")).upper(),
        "tool_name": enriched["tool_name"],
        "fit": "high",
        "risk": "low",
        "category": "dev_tool",
        "source_url": enriched["source_url"],
        "raw": enriched,
    }


# ---------------------------------------------------------------------------
# L → first press dry-run; second press within window goes live
# ---------------------------------------------------------------------------


def test_lab_first_press_is_dry_run(tmp_path, monkeypatch):
    """First press fires the worker with ``live=False`` (dry-run)."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        captured: list = []

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            scout._rows = [
                _seed_row(
                    {"tool_name": "requests", "source_url": "https://pypi.org/project/requests/"}
                )
            ]

            def _record(*, tool, url, live):
                captured.append({"tool": tool, "url": url, "live": live})

            scout._lab_worker = _record  # type: ignore[assignment]
            scout.action_lab_selected()
            await pilot.pause()
        assert captured, "L should have invoked the lab worker"
        assert captured[0]["live"] is False
        assert captured[0]["tool"] == "requests"

    asyncio.run(run())


def test_lab_double_press_state_machine(tmp_path, monkeypatch):
    """Textual's ``@work(exclusive=True)`` decorator wraps the method
    at class-definition time, so a plain monkeypatch can't intercept
    ``_lab_worker`` calls. We override the wrapped attribute on the
    *instance* with a plain function and assert the state-machine
    transitions through dry → live → dry across the confirmation
    window."""

    import time

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        captured: list = []

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            scout._rows = [_seed_row({"tool_name": "requests"})]

            # Replace the worker on the instance only.
            def _record(*, tool, url, live):
                captured.append({"tool": tool, "live": live})

            scout._lab_worker = _record  # type: ignore[assignment]

            scout.action_lab_selected()                          # first
            assert captured[-1]["live"] is False
            scout.action_lab_selected()                          # second, instant
            assert captured[-1]["live"] is True
            scout._last_lab_press = time.monotonic() - 10.0
            scout.action_lab_selected()
            assert captured[-1]["live"] is False
            await pilot.pause()
        assert len(captured) == 3

    asyncio.run(run())


# ---------------------------------------------------------------------------
# e → evaluate_url + evaluate_policy
# ---------------------------------------------------------------------------


def test_evaluate_invokes_evaluate_url(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        seen: dict = {}

        # Build a minimal fake evaluation chain.
        class _FakeManifest:
            tool_name = "fake/tool"
            source_url = "https://github.com/fake/tool"
            capabilities: dict = {}
            dangerous_flags: list = []

        class _FakeEvaluation:
            tool_name = "fake/tool"
            permission_manifest = _FakeManifest()

        def _fake_evaluate_url(url, stack):
            seen["url"] = url
            return _FakeEvaluation()

        class _FakeDecision:
            verdict = "trial"
            summary = "TRIAL — stubbed"
            findings: list = []

        def _fake_evaluate_policy(evaluation, manifest, policy=None):
            seen["policy_called"] = True
            return _FakeDecision()

        monkeypatch.setattr(
            "frontier_scout.evaluate.evaluate_url", _fake_evaluate_url
        )
        monkeypatch.setattr(
            "frontier_scout.policy.evaluate_policy", _fake_evaluate_policy
        )

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            row = _seed_row(
                {"tool_name": "fake/tool", "source_url": "https://github.com/fake/tool"}
            )
            scout._rows = [row]
            scout.action_evaluate_selected()
            await pilot.pause()
        await asyncio.sleep(0.5)
        assert seen.get("url") == "https://github.com/fake/tool"
        assert seen.get("policy_called") is True

    asyncio.run(run())


# ---------------------------------------------------------------------------
# D → build_dossier
# ---------------------------------------------------------------------------


def test_dossier_invokes_build_dossier_and_writes_file(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        seen: dict = {}

        def _fake_build_dossier(tool, repo=None):
            seen["tool"] = tool
            return {"tool_name": tool, "fake": True}

        monkeypatch.setattr(
            "frontier_scout.dossier.build_dossier", _fake_build_dossier
        )

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            row = _seed_row({"tool_name": "anthropics/skills"})
            scout._rows = [row]
            scout.action_dossier_selected()
            await pilot.pause()
        await asyncio.sleep(0.5)
        assert seen.get("tool") == "anthropics/skills"
        from frontier_scout.store import home_dir

        # The dossier file should have been written into ~/.frontier-scout/dossiers/.
        expected = home_dir() / "dossiers" / "anthropics-skills.json"
        assert expected.exists(), f"missing dossier file: {expected}"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------


def test_lab_skipped_on_dep_row(tmp_path, monkeypatch):
    """Pressing L on a dependency-finding row must not invoke the worker."""

    async def run() -> None:
        monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
        repo = _seed(tmp_path / "repo")
        diagnostics = setup_diagnostics(repo, ollama_timeout_s=0.001)

        from frontier_scout.tui.setup_app import SetupApp
        from frontier_scout.tui.tabs.scout_tab import ScoutTab

        captured: list = []

        app = SetupApp(diagnostics, show_splash=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            scout = app.query_one(ScoutTab)
            scout._rows = [
                {"kind": "dep", "verdict": "TRIAL", "tool_name": "pkg 1.0 → 1.1", "raw": {}}
            ]
            scout._lab_worker = (  # type: ignore[assignment]
                lambda **kw: captured.append(kw)
            )
            scout.action_lab_selected()
            await pilot.pause()
        assert not captured

    asyncio.run(run())
