"""v1.3.0 Stream A — ProgressReporter abstraction.

The backend reporter protocol must:

- be a true no-op when no reporter is passed (``NullReporter``) so
  existing CLI callers see zero behaviour change;
- record every event in order for tests (``RecordingReporter``);
- drive a stderr line for ``--progress`` callers without hijacking
  the TTY when stdout is being piped (``StderrReporter``);
- emit a sane sequence of stages from every backend wired in this
  stream: ``scout.run_scan`` (dry + live), ``run_dependency_scan``,
  ``run_guard``, ``evaluate_url``, ``build_dossier``.
"""

from __future__ import annotations

import io
from pathlib import Path

from frontier_scout.progress import (
    NullReporter,
    ProgressReporter,
    RecordingReporter,
    StderrReporter,
)


# ---------------------------------------------------------------------------
# Protocol + concrete implementations
# ---------------------------------------------------------------------------


def test_null_reporter_is_a_true_noop():
    r = NullReporter()
    # None of these should raise or set any state.
    r.stage("doesn't matter")
    r.stage("with total", total_stages=5)
    r.advance(0.5, "halfway")
    r.log("noise", tone="warn")
    # Protocol check — NullReporter must satisfy ProgressReporter.
    assert isinstance(r, ProgressReporter)


def test_recording_reporter_captures_events_in_order():
    r = RecordingReporter()
    r.stage("Detecting stack", total_stages=3)
    r.advance(0.3, "1/3 manifest")
    r.log("found 7 deps", tone="info")
    r.stage("Querying judge", total_stages=3)
    assert r.stages == ["Detecting stack", "Querying judge"]
    assert r.logs == ["found 7 deps"]
    assert r.events[1] == ("advance", {"fraction": 0.3, "message": "1/3 manifest"})


def test_recording_reporter_satisfies_protocol():
    assert isinstance(RecordingReporter(), ProgressReporter)


# ---------------------------------------------------------------------------
# StderrReporter — single \r line on TTY, newline-delimited on pipes
# ---------------------------------------------------------------------------


class _FakeStream(io.StringIO):
    """StringIO that fakes a TTY via the ``isatty`` flag."""

    def __init__(self, *, isatty: bool) -> None:
        super().__init__()
        self._isatty = isatty

    def isatty(self) -> bool:  # type: ignore[override]
        return self._isatty


def test_stderr_reporter_uses_carriage_return_when_tty():
    stream = _FakeStream(isatty=True)
    r = StderrReporter(stream=stream)
    r.stage("Detecting stack", total_stages=3)
    r.stage("Querying judge", total_stages=3)
    raw = stream.getvalue()
    # Both stages overwrite via \r; no trailing newline between them.
    assert raw.startswith("\r")
    assert raw.count("\r") == 2
    assert "Detecting stack" in raw
    assert "Querying judge [2/3]" in raw


def test_stderr_reporter_writes_newlines_when_piped():
    stream = _FakeStream(isatty=False)
    r = StderrReporter(stream=stream)
    r.stage("Detecting stack", total_stages=2)
    r.stage("Querying judge", total_stages=2)
    raw = stream.getvalue()
    # Pipe-friendly: one line per stage, no \r mash.
    assert "\r" not in raw
    assert raw.count("\n") == 2
    assert "Detecting stack" in raw


def test_stderr_reporter_advance_renders_percentage():
    stream = _FakeStream(isatty=True)
    r = StderrReporter(stream=stream)
    r.stage("Classifying upgrades", total_stages=2)
    r.advance(0.5, "3/6 fastapi")
    raw = stream.getvalue()
    assert "50%" in raw
    assert "3/6 fastapi" in raw


def test_stderr_reporter_clamps_fraction():
    stream = _FakeStream(isatty=False)
    r = StderrReporter(stream=stream)
    r.stage("x", total_stages=1)
    r.advance(2.5, "over")
    r.advance(-1.0, "under")
    raw = stream.getvalue()
    assert "100%" in raw
    assert "0%" in raw


def test_stderr_reporter_survives_broken_pipe():
    """A closed stream must not crash the worker that reports progress."""

    stream = _FakeStream(isatty=False)
    stream.close()
    r = StderrReporter(stream=stream)
    # No exception even though the stream is closed.
    r.stage("doesn't matter")
    r.advance(0.5)
    r.log("info")


# ---------------------------------------------------------------------------
# Backends emit a sane stage sequence
# ---------------------------------------------------------------------------


def test_run_scan_dry_run_emits_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
    from frontier_scout.scout import run_scan

    rec = RecordingReporter()
    payload = run_scan(repo=repo, dry_run=True, persist=False, reporter=rec)
    assert payload["verdicts"]
    # Must start with stack detect, end with personalising.
    assert rec.stages[0] == "Detecting stack"
    assert "Personalising verdicts" in rec.stages
    # The completion log line tells the TUI a successful scout finished.
    assert any("Scout complete" in m for m in rec.logs)


def test_run_scan_works_without_reporter(tmp_path, monkeypatch):
    """Back-compat: existing callers don't pass a reporter."""

    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
    from frontier_scout.scout import run_scan

    payload = run_scan(repo=repo, dry_run=True, persist=False)
    assert payload["verdicts"]


def test_run_dependency_scan_emits_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text(
        "fastapi==0.115.0\nrequests==2.31.0\n"
    )
    from frontier_scout.dependencies import run_dependency_scan

    rec = RecordingReporter()
    run_dependency_scan(repo, persist=False, reporter=rec)
    assert "Reading manifests" in rec.stages
    assert "Classifying upgrades" in rec.stages


def test_run_guard_emits_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    from frontier_scout.guard import run_guard

    rec = RecordingReporter()
    run_guard(reporter=rec)
    assert rec.stages == ["Loading ledger", "Applying policy"]


def test_evaluate_url_emits_stages():
    from frontier_scout.evaluate import evaluate_url

    rec = RecordingReporter()
    evaluation = evaluate_url("https://github.com/anthropics/skills", reporter=rec)
    assert evaluation.tool_name
    assert "Classifying capabilities" in rec.stages


def test_build_dossier_emits_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("fastapi==0.115.0\n")
    from frontier_scout.dossier import build_dossier

    rec = RecordingReporter()
    payload = build_dossier("anthropics/skills", repo=repo, reporter=rec)
    assert payload["tool_name"]
    assert "Gathering local signals" in rec.stages
    assert "Compiling brief" in rec.stages
