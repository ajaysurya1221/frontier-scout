"""v1.3.0 Stream F — CLI --progress flag.

Pin the contract: when ``--progress`` is passed, the staged scout
events show up on stderr without breaking the JSON / plain-text
output on stdout. Default off so existing CI / pipeline callers
see no change.
"""

from __future__ import annotations

import json
import subprocess
import sys


def test_scan_progress_streams_to_stderr_without_clobbering_json(tmp_path):
    """``scan --dry-run --progress --json`` must:

    1. Print the JSON payload to stdout intact (so callers can pipe
       it through ``jq`` like they always have).
    2. Stream the staged event lines to stderr.
    """

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
    home = tmp_path / "home"

    env = {"FRONTIER_SCOUT_HOME": str(home), "PATH": "/usr/bin:/bin"}

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "frontier_scout",
            "scan",
            "--dry-run",
            "--repo",
            str(repo),
            "--json",
            "--progress",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    # stdout is valid JSON.
    payload = json.loads(proc.stdout)
    assert "verdicts" in payload

    # stderr carries the staged events.
    assert "Detecting stack" in proc.stderr
    assert "Personalising verdicts" in proc.stderr


def test_scan_without_progress_emits_no_stderr_chatter(tmp_path):
    """``--progress`` is opt-in — without it, stderr stays empty."""

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
    home = tmp_path / "home"

    env = {"FRONTIER_SCOUT_HOME": str(home), "PATH": "/usr/bin:/bin"}

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "frontier_scout",
            "scan",
            "--dry-run",
            "--repo",
            str(repo),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    # The CLI may still print warnings (textual missing extras etc) on
    # stderr — what we pin is that no progress markers leak through.
    assert "Detecting stack" not in proc.stderr
    assert "Personalising verdicts" not in proc.stderr
