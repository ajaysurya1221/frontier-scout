"""Append-only quality observability ledger.

Every Scout run logs one JSON record to ``quality-log.jsonl`` with funnel
stats, judge metrics, cost, and duration. Used to track signal-to-noise
over time and detect quality regressions before they ship.

Storage location follows the same ``FRONTIER_SCOUT_HOME`` convention as
:mod:`cost_tracker` — production CLI writes to ``~/.frontier-scout/``,
development runs fall back to the repo root.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def _log_path() -> Path:
    home_env = os.environ.get("FRONTIER_SCOUT_HOME")
    if home_env:
        return Path(home_env).expanduser() / "quality-log.jsonl"
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "quality-log.jsonl"


QUALITY_LOG = _log_path()


def log_run(component: str, **stats) -> None:
    """Append one quality record. ``component`` is typically ``"scout"``.

    Recommended stats keys (all optional, log whatever's available):
        items_scanned, dedup_drops, seen_drops, candidates,
        verdicts_pre_judge, verdicts_post_judge, policy_dropped,
        judge_self_rating, judge_used_fallback,
        total_cost_usd, duration_s, output_written,
        llm_retries_total, llm_retries_by_component,
        crashed, error_type, error_msg
    """
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "component": component,
        **stats,
    }
    QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUALITY_LOG.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
