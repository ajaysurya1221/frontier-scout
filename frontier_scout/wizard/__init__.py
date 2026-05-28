"""Setup wizard for ``frontier-scout setup``.

Standalone Textual App that walks a user through:
1. Welcome + safety contract.
2. LLM backend choice (auto-detection + copy-friendly setup commands).
3. Mode choice — Automation (recurring scouts) vs Ad-hoc (manual).
4a. Automation: pick repos + cron schedule + notification channel,
    install the cron-runner, surface the one crontab line.
4b. Ad-hoc: how-to screen with the exact commands the user can run.

The wizard persists chosen settings to ``~/.frontier-scout/config.toml``
and ``~/.frontier-scout/schedules.json`` via the existing helpers in
``frontier_scout/scheduling.py``. Keys are never written to disk by us.

For non-interactive use (CI, scripts): see
``frontier_scout/wizard/headless.py`` for the same flow without a TUI.
"""

from frontier_scout.wizard.app import WizardApp
from frontier_scout.wizard.headless import run_headless

__all__ = ["WizardApp", "run_headless"]
