"""Stream I — setup persistence is honored.

Before v1.2.1, ``frontier-scout setup`` blindly re-ran the wizard
every time, and the bare ``frontier-scout`` ignored
``~/.frontier-scout/config.toml``. These tests pin the new contract:

- Bare ``frontier-scout`` from an onboarded user → straight to the TUI
  (no wizard intro).
- ``frontier-scout setup`` from an onboarded interactive user → prompted
  to confirm.
- ``frontier-scout setup`` from an onboarded non-interactive user → no-op
  unless ``--force``.
- ``frontier-scout --setup`` (top-level alias) is equivalent to the
  subcommand form.
"""

from __future__ import annotations

import io
import os

import pytest

from frontier_scout import cli
from frontier_scout.wizard.config import mark_wizard_complete


@pytest.fixture
def fresh_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    yield tmp_path


def _stub_runner(record):
    def runner(**kwargs):
        record["called"] = True
        record["kwargs"] = kwargs
        return 0

    return runner


# ---------------------------------------------------------------------------
# Bare ``frontier-scout``
# ---------------------------------------------------------------------------


def test_bare_run_skips_wizard_for_onboarded_user(fresh_home, monkeypatch):
    mark_wizard_complete()  # writes config.toml in the fresh home

    record: dict = {"wizard_called": False, "tui_called": False}

    class _FakeWizard:
        def run(self):  # pragma: no cover — must NOT run
            record["wizard_called"] = True
            return "open-tui"

    def _fake_run_setup(**kwargs):
        record["tui_called"] = True
        record["tui_kwargs"] = kwargs
        return 0

    monkeypatch.setattr("frontier_scout.wizard.app.WizardApp", _FakeWizard)
    monkeypatch.setattr("frontier_scout.tui.runner.run_setup", _fake_run_setup)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)

    # v1.5.0 makes the Briefing the bare-run default; the wizard +
    # run_setup onboarding contract this test pins lives on the classic UI.
    rc = cli.main(["--ui", "classic"])
    assert rc == 0
    assert record["wizard_called"] is False
    assert record["tui_called"] is True


def test_bare_run_invokes_wizard_for_first_time_user(fresh_home, monkeypatch):
    record: dict = {"wizard_called": False, "tui_called": False}

    class _FakeWizard:
        def run(self):
            record["wizard_called"] = True
            return "open-tui"

    def _fake_run_setup(**kwargs):
        record["tui_called"] = True
        return 0

    monkeypatch.setattr("frontier_scout.wizard.app.WizardApp", _FakeWizard)
    monkeypatch.setattr("frontier_scout.tui.runner.run_setup", _fake_run_setup)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)

    # First-run wizard onboarding is a classic-UI contract (the Briefing,
    # the v1.5.0 default, is self-contained).
    cli.main(["--ui", "classic"])
    assert record["wizard_called"] is True
    assert record["tui_called"] is True


# ---------------------------------------------------------------------------
# ``frontier-scout setup`` for an onboarded user
# ---------------------------------------------------------------------------


def test_setup_onboarded_non_interactive_is_noop(fresh_home, monkeypatch, capsys):
    mark_wizard_complete()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    rc = cli.main(["setup"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "already onboarded" in out.lower()


def test_setup_onboarded_interactive_declines(fresh_home, monkeypatch, capsys):
    """User says "N" at the prompt → wizard does NOT run."""

    mark_wizard_complete()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")

    record: dict = {"wizard_called": False}

    class _FakeWizard:
        def run(self):  # pragma: no cover
            record["wizard_called"] = True
            return "open-tui"

    monkeypatch.setattr("frontier_scout.wizard.app.WizardApp", _FakeWizard)

    rc = cli.main(["setup"])
    assert rc == 0
    assert record["wizard_called"] is False
    assert "unchanged" in capsys.readouterr().out.lower()


def test_setup_force_overrides_onboarded(fresh_home, monkeypatch):
    """``--force`` re-runs the wizard even when onboarded."""

    mark_wizard_complete()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)

    record: dict = {"wizard_called": False}

    class _FakeWizard:
        def run(self):
            record["wizard_called"] = True
            return "open-tui"

    def _fake_run_setup(**kwargs):
        return 0

    monkeypatch.setattr("frontier_scout.wizard.app.WizardApp", _FakeWizard)
    monkeypatch.setattr("frontier_scout.tui.runner.run_setup", _fake_run_setup)

    rc = cli.main(["setup", "--force"])
    assert rc == 0
    assert record["wizard_called"] is True


# ---------------------------------------------------------------------------
# ``--setup`` alias
# ---------------------------------------------------------------------------


def test_top_level_setup_alias_routes_to_setup_subcommand(fresh_home, monkeypatch, capsys):
    """``frontier-scout --setup`` should behave like ``frontier-scout setup``."""

    mark_wizard_complete()  # so the prompt path is exercised
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)

    rc = cli.main(["--setup"])
    assert rc == 0
    assert "already onboarded" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# ``--demo`` alias
# ---------------------------------------------------------------------------


def test_top_level_demo_alias_routes_to_demo_subcommand(fresh_home, tmp_path, capsys):
    """``frontier-scout --demo`` should behave like ``frontier-scout demo``,
    and accept the demo subcommand's own flags (``--no-serve``)."""

    out_dir = tmp_path / "demo-out"
    rc = cli.main(["--demo", "--no-serve", "--output-dir", str(out_dir)])
    assert rc == 0
    captured = capsys.readouterr().out.lower()
    assert "html report" in captured
    assert (out_dir / "briefing.html").exists()
    assert (out_dir / "verdicts.json").exists()


def test_provider_flag_sets_env_before_subcommand(fresh_home, tmp_path, monkeypatch):
    """``--provider`` pins FRONTIER_SCOUT_PROVIDER in any position."""

    monkeypatch.delenv("FRONTIER_SCOUT_PROVIDER", raising=False)
    out_dir = tmp_path / "p1"
    rc = cli.main(["--provider", "openai", "--demo", "--no-serve", "--output-dir", str(out_dir)])
    assert rc == 0
    assert os.environ["FRONTIER_SCOUT_PROVIDER"] == "openai"


def test_provider_flag_equals_form_after_subcommand(fresh_home, tmp_path, monkeypatch):
    """``--provider=X`` after the subcommand also works."""

    monkeypatch.delenv("FRONTIER_SCOUT_PROVIDER", raising=False)
    out_dir = tmp_path / "p2"
    rc = cli.main(["demo", "--no-serve", "--output-dir", str(out_dir), "--provider=claude-cli"])
    assert rc == 0
    assert os.environ["FRONTIER_SCOUT_PROVIDER"] == "claude-cli"


# ---------------------------------------------------------------------------
# Reconfigure exit code 42 — Stream N hook tested via CLI
# ---------------------------------------------------------------------------


def test_reconfigure_exit_code_relaunches_wizard(fresh_home, monkeypatch):
    """If the TUI exits with 42, ``main`` runs the wizard then re-enters
    the TUI. After the second TUI returns 0, ``main`` returns 0."""

    mark_wizard_complete()  # so first launch goes straight to TUI

    calls: list = []

    def _fake_run_setup(**kwargs):
        calls.append("tui")
        return cli.RECONFIGURE_EXIT_CODE if len(calls) == 1 else 0

    class _FakeWizard:
        def run(self):
            calls.append("wizard")
            return "open-tui"

    monkeypatch.setattr("frontier_scout.tui.runner.run_setup", _fake_run_setup)
    monkeypatch.setattr("frontier_scout.wizard.app.WizardApp", _FakeWizard)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)

    # The reconfigure (exit-42) relaunch loop wraps the classic UI.
    rc = cli.main(["--ui", "classic"])
    assert rc == 0
    assert calls == ["tui", "wizard", "tui"]
