# tests/test_cli_bare_help.py
"""Bare `frontier-scout` (no subcommand) should print help, never auto-launch
the TUI — even in an interactive terminal. The TUI stays reachable via the
explicit `open` command and `--ui`."""

import sys

import frontier_scout.cli as cli_mod
from frontier_scout.cli import main


def test_bare_command_prints_help_and_never_launches_tui(monkeypatch, capsys):
    # Simulate an interactive terminal (both streams report TTY).
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)

    # Guard: a bare invocation must NOT enter the Mission Control launch path.
    launched = {"tui": False}
    monkeypatch.setattr(
        cli_mod,
        "_run_tui_with_reconfigure_loop",
        lambda *a, **k: (launched.__setitem__("tui", True), 0)[1],
    )

    rc = main([])
    out = capsys.readouterr().out

    assert launched["tui"] is False, "bare `frontier-scout` must not launch the TUI"
    assert rc == 0
    assert "usage" in out.lower()
    assert "agent" in out  # subcommands are listed on the help screen


def test_explicit_ui_flag_still_launches_the_tui(monkeypatch):
    # An explicit `--ui mission` is a deliberate request — it must still launch.
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    launched = {"tui": False}
    monkeypatch.setattr(
        cli_mod,
        "_run_tui_with_reconfigure_loop",
        lambda *a, **k: (launched.__setitem__("tui", True), 0)[1],
    )
    rc = main(["--ui", "mission"])
    assert launched["tui"] is True, "explicit --ui mission must still launch Mission Control"
    assert rc == 0
