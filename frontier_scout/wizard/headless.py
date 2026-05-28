"""Non-interactive setup wizard.

Used by CI, scripts, and the CLI fallback when the terminal isn't a TTY.
"""

from __future__ import annotations

from pathlib import Path

from frontier_scout.scheduling import (
    add_schedule,
    crontab_line,
    install_cron_runner,
    is_valid_cron_expr,
)
from frontier_scout.wizard.config import (
    mark_wizard_complete,
    update_llm,
    update_mode,
)


def run_headless(
    *,
    mode: str = "adhoc",
    llm: str | None = None,
    repos: list[str] | None = None,
    cron_expr: str = "@daily",
    notification: str = "file",
) -> dict:
    """Apply the wizard's choices without showing UI.

    Returns a dict describing what was written and the crontab line the
    user still needs to add (when mode == 'automation').
    """

    if mode not in ("automation", "adhoc"):
        raise ValueError(f"unknown mode: {mode!r}")
    if llm:
        update_llm(llm)
    update_mode(mode)

    result: dict = {"mode": mode, "llm": llm}

    if mode == "automation":
        if not repos:
            raise ValueError("automation mode requires at least one repo")
        if not is_valid_cron_expr(cron_expr):
            raise ValueError(f"invalid cron expression: {cron_expr!r}")
        runner = install_cron_runner()
        schedules = []
        for repo in repos:
            path = Path(repo).expanduser().resolve()
            schedules.append(
                add_schedule(path, cron_expr=cron_expr, notification=notification)
            )
        result["schedules"] = [s.to_dict() for s in schedules]
        result["cron_runner"] = str(runner)
        result["crontab_line"] = crontab_line()

    mark_wizard_complete()
    return result
