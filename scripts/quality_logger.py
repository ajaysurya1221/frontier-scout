"""
Append-only quality observability ledger.

Every Scout / Pulse / Synth run logs one JSON record to quality-log.jsonl with
funnel stats, judge metrics, cost, and duration. Used to track signal-to-noise
over time and detect quality regressions before they ship.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
QUALITY_LOG = REPO_ROOT / "quality-log.jsonl"


def log_run(component: str, **stats) -> None:
    """
    Append one quality record. `component` is one of:
      "scout" | "pulse" | "synth"

    Recommended stats keys (all optional, log whatever's available):
      items_scanned, dedup_drops, mem0_prior_drops, candidates,
      verdicts_pre_judge, verdicts_post_judge, vetoed, tier_adjusted,
      missed_recovered, judge_self_rating, total_cost_usd, duration_s,
      arxiv_status, slack_posted
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": component,
        **stats,
    }
    QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUALITY_LOG.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
