"""Cron-based scheduling for recurring scout runs.

Stores schedules in ``~/.frontier-scout/schedules.json``, generates a
shell runner the user adds to their crontab once, and provides a
headless ``run_due()`` invoked by ``frontier-scout cron run``.

No surprise side effects: we never install crontab entries ourselves —
we generate the one-liner and show it for the user to add. We never
write secrets. We never reach the network unless an underlying live
scan does.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frontier_scout.store import home_dir, init_home

_CRON_MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}


@dataclass
class Schedule:
    id: str
    repo: str
    cron_expr: str
    notification: str = "file"  # file | system | disabled
    last_run: str | None = None
    last_result_dir: str | None = None
    last_verdict_count: int = 0
    disabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schedule:
        return cls(
            id=str(data.get("id", _new_id())),
            repo=str(data.get("repo", "")),
            cron_expr=str(data.get("cron_expr", "@daily")),
            notification=str(data.get("notification", "file")),
            last_run=data.get("last_run"),
            last_result_dir=data.get("last_result_dir"),
            last_verdict_count=int(data.get("last_verdict_count") or 0),
            disabled=bool(data.get("disabled", False)),
        )


def schedules_path() -> Path:
    return home_dir() / "schedules.json"


def cron_runner_path() -> Path:
    return home_dir() / "cron-runner.sh"


def runs_dir() -> Path:
    return home_dir() / "runs"


def load_schedules() -> list[Schedule]:
    path = schedules_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("schedules") if isinstance(data, dict) else []
    return [Schedule.from_dict(item) for item in (raw or [])]


def save_schedules(schedules: list[Schedule]) -> Path:
    path = schedules_path()
    init_home()
    payload = {"schedules": [s.to_dict() for s in schedules]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def add_schedule(repo: Path | str, *, cron_expr: str = "@daily", notification: str = "file") -> Schedule:
    schedules = load_schedules()
    resolved = str(Path(str(repo)).expanduser().resolve())
    sched = Schedule(id=_new_id(), repo=resolved, cron_expr=cron_expr, notification=notification)
    schedules.append(sched)
    save_schedules(schedules)
    return sched


def remove_schedule(schedule_id: str) -> bool:
    schedules = load_schedules()
    remaining = [s for s in schedules if s.id != schedule_id]
    if len(remaining) == len(schedules):
        return False
    save_schedules(remaining)
    return True


def install_cron_runner() -> Path:
    """Write the cron-runner shell script. Idempotent; preserves the
    existing file if its content already matches."""

    init_home()
    path = cron_runner_path()
    body = (
        "#!/usr/bin/env bash\n"
        "# Frontier Scout cron runner — installed by `frontier-scout setup`.\n"
        "# Pass-through of HOME and PATH only; nothing else inherited.\n"
        "exec /usr/bin/env -i HOME=\"$HOME\" PATH=\"$PATH\" frontier-scout cron run "
        ">> \"$HOME/.frontier-scout/cron.log\" 2>&1\n"
    )
    if path.exists() and path.read_text() == body:
        return path
    path.write_text(body)
    try:
        path.chmod(0o755)
    except OSError:
        # On some filesystems chmod is a no-op; the user can adjust manually.
        pass
    return path


def crontab_line() -> str:
    """Return the single crontab line the user adds once."""

    return f'*/15 * * * * "{cron_runner_path()}"'


def normalise_cron_expr(expr: str) -> str:
    """Return the canonical 5-field expression for a macro or pass-through."""

    expr = expr.strip()
    return _CRON_MACROS.get(expr.lower(), expr)


def is_valid_cron_expr(expr: str) -> bool:
    """Validate using croniter when available; fall back to macro-only."""

    canonical = normalise_cron_expr(expr)
    try:
        from croniter import croniter  # type: ignore
    except ImportError:
        return expr.lower() in _CRON_MACROS
    try:
        croniter(canonical, datetime.now(tz=UTC))
        return True
    except (ValueError, KeyError):
        return False


def is_due(schedule: Schedule, *, now: datetime | None = None, grace_minutes: int = 15) -> bool:
    """Return True if ``schedule`` should fire at ``now``.

    Strategy: walk backward from `now` to find the most recent prior fire
    time according to the cron expression. If that fire time is more
    recent than ``last_run`` (and within `grace_minutes` of now), the
    schedule is due.
    """

    if schedule.disabled:
        return False
    canonical = normalise_cron_expr(schedule.cron_expr)
    now_utc = (now or datetime.now(tz=UTC)).replace(microsecond=0)
    try:
        from croniter import croniter  # type: ignore
    except ImportError:
        # Fallback: only handle macros — fire if last_run is older than one period.
        period_seconds = {
            "@hourly": 3600,
            "@daily": 86400,
            "@midnight": 86400,
            "@weekly": 604800,
            "@monthly": 2592000,
        }.get(schedule.cron_expr.lower())
        if period_seconds is None:
            return False
        if schedule.last_run is None:
            return True
        try:
            last = datetime.fromisoformat(schedule.last_run.replace("Z", "+00:00"))
        except ValueError:
            return True
        return (now_utc - last).total_seconds() >= period_seconds
    try:
        prev = croniter(canonical, now_utc).get_prev(datetime)
    except (ValueError, KeyError):
        return False
    if schedule.last_run is None:
        return True
    try:
        last = datetime.fromisoformat(schedule.last_run.replace("Z", "+00:00"))
    except ValueError:
        return True
    return prev > last


def record_run(
    schedule: Schedule,
    *,
    result_dir: Path,
    verdict_count: int,
    now: datetime | None = None,
) -> None:
    now_utc = (now or datetime.now(tz=UTC)).replace(microsecond=0)
    schedule.last_run = now_utc.isoformat().replace("+00:00", "Z")
    schedule.last_result_dir = str(result_dir)
    schedule.last_verdict_count = verdict_count
    schedules = load_schedules()
    updated = [schedule if s.id == schedule.id else s for s in schedules]
    save_schedules(updated)


def run_due(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """Execute every due schedule. Returns a list of result summaries.

    Each result has ``schedule_id``, ``repo``, ``ran``, ``verdict_count``,
    and ``result_dir`` (or ``error`` if execution failed).
    """

    from frontier_scout.notifications import notify_new_verdicts
    from frontier_scout.scout import run_scan

    results: list[dict[str, Any]] = []
    for schedule in load_schedules():
        if not is_due(schedule):
            continue
        repo = Path(schedule.repo)
        if not repo.exists() or not repo.is_dir():
            results.append(
                {
                    "schedule_id": schedule.id,
                    "repo": schedule.repo,
                    "ran": False,
                    "error": "repo missing or not a directory",
                }
            )
            continue
        result_dir = _make_run_dir(schedule)
        try:
            payload = run_scan(repo=repo, dry_run=dry_run, persist=True)
        except Exception as exc:  # noqa: BLE001 — propagate as data
            results.append(
                {
                    "schedule_id": schedule.id,
                    "repo": schedule.repo,
                    "ran": False,
                    "error": str(exc),
                }
            )
            continue
        verdicts = list(payload.get("verdicts") or [])
        (result_dir / "verdicts.json").write_text(json.dumps(payload, indent=2, default=str))
        record_run(schedule, result_dir=result_dir, verdict_count=len(verdicts))
        notify_new_verdicts(schedule=schedule, verdicts=verdicts, result_dir=result_dir)
        results.append(
            {
                "schedule_id": schedule.id,
                "repo": schedule.repo,
                "ran": True,
                "verdict_count": len(verdicts),
                "result_dir": str(result_dir),
            }
        )
    return results


def _new_id() -> str:
    return secrets.token_hex(6)


def _make_run_dir(schedule: Schedule) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    target = runs_dir() / schedule.id / stamp
    target.mkdir(parents=True, exist_ok=True)
    return target


__all__ = [
    "Schedule",
    "add_schedule",
    "cron_runner_path",
    "crontab_line",
    "install_cron_runner",
    "is_due",
    "is_valid_cron_expr",
    "load_schedules",
    "normalise_cron_expr",
    "record_run",
    "remove_schedule",
    "run_due",
    "save_schedules",
    "schedules_path",
]


# ``os`` re-export for tests that monkeypatch environment.
_ = os
