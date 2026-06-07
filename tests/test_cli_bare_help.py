# tests/test_cli_bare_help.py
"""A bare `frontier-scout` (no subcommand) prints help and exits cleanly."""

from frontier_scout.cli import main


def test_bare_command_prints_help(capsys):
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "usage" in out.lower()
    assert "agent" in out  # subcommands are listed on the help screen


def test_version_flag(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:  # argparse --version exits 0
        assert exc.code == 0
    assert "frontier-scout" in capsys.readouterr().out
