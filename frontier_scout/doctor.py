"""Self-diagnostics for Frontier Scout.

Run interactively via ``frontier-scout doctor`` or in JSON mode via
``frontier-scout doctor --json``. Every check is read-only and reports
``ok`` / ``warn`` / ``fail`` plus an actionable next-step.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from frontier_scout import __version__
from frontier_scout.scheduling import cron_runner_path, load_schedules, schedules_path
from frontier_scout.store import db_path, home_dir


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_doctor() -> list[Check]:
    return [
        _check_python_version(),
        _check_frontier_version(),
        _check_textual(),
        _check_tree_sitter(),
        _check_home_dir(),
        _check_sqlite(),
        _check_schedules(),
        _check_cron_runner(),
        _check_optional_clis(),
        _check_optional_notifiers(),
    ]


def render_text(checks: list[Check]) -> str:
    lines = ["Frontier Scout · self-check", ""]
    glyphs = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}
    for check in checks:
        glyph = glyphs.get(check.status, " ")
        lines.append(f"{glyph} {check.name}: {check.detail}")
        if check.fix and check.status != "ok":
            lines.append(f"     ↳ {check.fix}")
    bad = sum(1 for c in checks if c.status == "fail")
    warn = sum(1 for c in checks if c.status == "warn")
    summary = "\nall systems go." if bad == 0 and warn == 0 else (
        f"\n{bad} fail · {warn} warn · {len(checks) - bad - warn} ok"
    )
    lines.append(summary)
    return "\n".join(lines) + "\n"


def render_json(checks: list[Check]) -> str:
    return json.dumps(
        {
            "checks": [c.to_dict() for c in checks],
            "summary": {
                "fail": sum(1 for c in checks if c.status == "fail"),
                "warn": sum(1 for c in checks if c.status == "warn"),
                "ok": sum(1 for c in checks if c.status == "ok"),
            },
        },
        indent=2,
    )


def _check_python_version() -> Check:
    major, minor = sys.version_info.major, sys.version_info.minor
    if (major, minor) >= (3, 11):
        return Check("Python", "ok", f"{major}.{minor} (>= 3.11 required)")
    return Check(
        "Python",
        "fail",
        f"{major}.{minor}",
        fix="Frontier Scout requires Python 3.11+; install a newer interpreter.",
    )


def _check_frontier_version() -> Check:
    return Check("Frontier Scout", "ok", f"v{__version__}")


def _check_textual() -> Check:
    try:
        textual_version = version("textual")
        return Check("Textual", "ok", f"v{textual_version}")
    except PackageNotFoundError:
        return Check(
            "Textual",
            "fail",
            "package not installed",
            fix="pip install 'textual>=8.2,<9'",
        )


def _check_tree_sitter() -> Check:
    try:
        pack_version = version("tree-sitter-language-pack")
    except PackageNotFoundError:
        return Check(
            "tree-sitter-language-pack",
            "warn",
            "not installed — import-evidence scanner will degrade",
            fix="pip install 'tree-sitter-language-pack>=1.8,<2'",
        )
    try:
        from tree_sitter_language_pack import get_parser  # type: ignore

        get_parser("python")
        return Check("tree-sitter-language-pack", "ok", f"v{pack_version} · python parser ready")
    except Exception as exc:  # noqa: BLE001
        return Check(
            "tree-sitter-language-pack",
            "warn",
            f"installed but parser load failed: {exc}",
            fix="Try `pip install --upgrade tree-sitter-language-pack`.",
        )


def _check_home_dir() -> Check:
    home = home_dir()
    try:
        home.mkdir(parents=True, exist_ok=True)
        test = home / ".doctor-write-test"
        test.write_text("ok")
        test.unlink()
        return Check("home directory", "ok", str(home))
    except OSError as exc:
        return Check(
            "home directory",
            "fail",
            f"{home} not writable: {exc}",
            fix="Check filesystem permissions on ~/.frontier-scout/.",
        )


def _check_sqlite() -> Check:
    path = db_path()
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("SELECT 1").fetchone()
        return Check("local SQLite", "ok", str(path))
    except sqlite3.Error as exc:
        return Check(
            "local SQLite",
            "fail",
            f"cannot open {path}: {exc}",
            fix="Try `frontier-scout clear-history --all` to reset, or delete the file.",
        )


def _check_schedules() -> Check:
    try:
        schedules = load_schedules()
    except Exception as exc:  # noqa: BLE001
        return Check(
            "schedules.json",
            "fail",
            f"parse error: {exc}",
            fix=f"Inspect or remove {schedules_path()}.",
        )
    if not schedules:
        return Check(
            "schedules.json",
            "ok",
            "no schedules registered (ad-hoc mode)",
        )
    return Check(
        "schedules.json",
        "ok",
        f"{len(schedules)} schedule(s) registered",
    )


def _check_cron_runner() -> Check:
    path = cron_runner_path()
    if not path.exists():
        return Check(
            "cron runner",
            "warn",
            "no cron-runner.sh — schedules won't fire automatically",
            fix="Run `frontier-scout setup` and pick Automation to install one.",
        )
    if not os.access(path, os.X_OK):
        return Check(
            "cron runner",
            "warn",
            f"{path} is not executable",
            fix=f"chmod +x {path}",
        )
    return Check("cron runner", "ok", str(path))


def _check_optional_clis() -> Check:
    found = []
    missing = []
    for tool in ("ollama", "claude", "codex"):
        if shutil.which(tool):
            found.append(tool)
        else:
            missing.append(tool)
    if not found:
        return Check(
            "optional model CLIs",
            "warn",
            "none found on PATH — only Local deterministic available",
            fix="Install `ollama` for local models, or `claude` / `codex` for vendor CLIs.",
        )
    detail = f"found: {', '.join(found)}"
    if missing:
        detail += f" · missing: {', '.join(missing)}"
    return Check("optional model CLIs", "ok", detail)


def _check_optional_notifiers() -> Check:
    if shutil.which("terminal-notifier"):
        return Check("system notifier", "ok", "terminal-notifier on PATH")
    if shutil.which("notify-send"):
        return Check("system notifier", "ok", "notify-send on PATH")
    return Check(
        "system notifier",
        "warn",
        "no terminal-notifier or notify-send found — file notifications still work",
        fix="brew install terminal-notifier (macOS) or apt install libnotify-bin (Linux).",
    )


__all__ = ["Check", "render_json", "render_text", "run_doctor"]
