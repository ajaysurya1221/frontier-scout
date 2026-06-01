"""Tests for the doctor self-diagnostics."""

from __future__ import annotations

import json

from frontier_scout.doctor import render_json, render_text, run_doctor


def test_doctor_returns_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    checks = run_doctor()
    # Must include Python, Textual, tree-sitter, SQLite, schedules.
    names = {c.name for c in checks}
    for required in ("Python", "Textual", "home directory", "local SQLite", "schedules.json"):
        assert required in names


def test_doctor_text_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    text = render_text(run_doctor())
    assert "Frontier Scout · self-check" in text


def test_doctor_json_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    payload = json.loads(render_json(run_doctor()))
    assert "checks" in payload
    assert "summary" in payload
    assert payload["summary"]["ok"] >= 1


def test_doctor_passes_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTIER_SCOUT_HOME", str(tmp_path / "home"))
    checks = run_doctor()
    # Critical baseline: Python and Textual must be ok.
    python_check = next(c for c in checks if c.name == "Python")
    textual_check = next(c for c in checks if c.name == "Textual")
    assert python_check.status == "ok"
    assert textual_check.status == "ok"
