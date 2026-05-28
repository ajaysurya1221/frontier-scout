"""Notifications for new ADOPT/TRIAL verdicts found by scheduled scouts.

Writes durable JSON files under ``~/.frontier-scout/notifications/`` so
the TUI's brand-bar `(N new)` chip and ``frontier-scout notifications
list`` always see the same source of truth. Optionally fires a system
notification (``terminal-notifier`` on macOS, ``notify-send`` on
Linux) when configured.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from frontier_scout.store import home_dir, init_home

if TYPE_CHECKING:
    from frontier_scout.scheduling import Schedule


def notifications_dir() -> Path:
    return home_dir() / "notifications"


def list_notifications(unread_only: bool = False) -> list[dict[str, Any]]:
    init_home()
    base = notifications_dir()
    if not base.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        data["_path"] = str(path)
        if unread_only and data.get("read"):
            continue
        items.append(data)
    return items


def unread_count() -> int:
    return len([n for n in list_notifications(unread_only=True) if not n.get("read")])


def mark_read(path: str) -> None:
    target = Path(path)
    if not target.exists():
        return
    try:
        data = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return
    data["read"] = True
    target.write_text(json.dumps(data, indent=2, default=str))


def clear_all() -> int:
    base = notifications_dir()
    if not base.exists():
        return 0
    count = 0
    for path in base.glob("*.json"):
        try:
            path.unlink()
            count += 1
        except OSError:
            continue
    return count


def write_notification(
    *,
    repo: str,
    schedule_id: str,
    new_verdicts: list[dict[str, Any]],
    result_dir: Path,
) -> Path | None:
    if not new_verdicts:
        return None
    init_home()
    base = notifications_dir()
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    path = base / f"{stamp}-{schedule_id}.json"
    payload = {
        "schedule_id": schedule_id,
        "repo": repo,
        "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "result_dir": str(result_dir),
        "new_verdicts": [
            {
                "tool_name": v.get("tool_name"),
                "verdict": v.get("verdict"),
                "fit": v.get("fit"),
                "risk": v.get("risk"),
                "source_url": v.get("source_url"),
            }
            for v in new_verdicts
        ],
        "read": False,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def notify_new_verdicts(
    *,
    schedule: Schedule,
    verdicts: list[dict[str, Any]],
    result_dir: Path,
) -> Path | None:
    """Diff against the prior persisted scan for this repo; write a
    notification if any tools are newly ADOPT or TRIAL."""

    if schedule.notification == "disabled":
        return None
    new = _diff_new_recommendations(repo=schedule.repo, verdicts=verdicts)
    if not new:
        return None
    path = write_notification(
        repo=schedule.repo,
        schedule_id=schedule.id,
        new_verdicts=new,
        result_dir=result_dir,
    )
    if path and schedule.notification == "system":
        _emit_system_notification(
            title=f"Frontier Scout · {Path(schedule.repo).name}",
            message=f"{len(new)} new adoption candidate(s)",
        )
    return path


def _diff_new_recommendations(
    *, repo: str, verdicts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return verdicts whose `tool_name` was not previously ADOPT/TRIAL
    for this repo. Reads the prior persisted scan from SQLite."""

    from frontier_scout.store import previous_scan_verdicts

    prior = previous_scan_verdicts(repo=repo)
    prior_recommended = {
        str(v.get("tool_name", "")).lower()
        for v in prior
        if str(v.get("verdict", "")).lower() in ("adopt", "trial")
    }
    new: list[dict[str, Any]] = []
    for v in verdicts:
        verdict = str(v.get("verdict", "")).lower()
        if verdict not in ("adopt", "trial"):
            continue
        tool = str(v.get("tool_name", "")).lower()
        if tool and tool not in prior_recommended:
            new.append(v)
    return new


def _emit_system_notification(*, title: str, message: str) -> None:
    """Fire a desktop notification if a supported binary is on PATH."""

    if shutil.which("terminal-notifier"):
        cmd = ["terminal-notifier", "-title", title, "-message", message]
    elif shutil.which("notify-send"):
        cmd = ["notify-send", title, message]
    else:
        return
    try:
        subprocess.run(cmd, check=False, timeout=2, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        # Notifications are best-effort.
        pass


__all__ = [
    "clear_all",
    "list_notifications",
    "mark_read",
    "notifications_dir",
    "notify_new_verdicts",
    "unread_count",
    "write_notification",
]
