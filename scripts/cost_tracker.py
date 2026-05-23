"""Append-only cost ledger.

Every Anthropic API call appends one JSON record to ``costs.jsonl`` with
token counts, dollar cost, and cache-hit metrics. The CLI's ``cost``
subcommand and the lab runner's daily-cap checker both read from this file.

Storage location:
  * If the env var ``FRONTIER_SCOUT_HOME`` is set, the ledger lives at
    ``$FRONTIER_SCOUT_HOME/costs.jsonl`` — this is the production path
    set by ``fs_cli/__main__.py`` to ``~/.frontier-scout/costs.jsonl``.
  * Otherwise it falls back to ``<repo>/costs.jsonl`` — useful for
    ``python scripts/scout.py`` development runs without setting up the
    CLI side.

Pricing verified 2026-05-20; update :data:`PRICING` if Anthropic changes
their list price.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _ledger_path() -> Path:
    home_env = os.environ.get("FRONTIER_SCOUT_HOME")
    if home_env:
        return Path(home_env).expanduser() / "costs.jsonl"
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "costs.jsonl"


LEDGER = _ledger_path()


# Per-MTok pricing. Cache reads ~10% of input; cache writes ~125%.
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00,
        "cache_read":  0.30,
        "cache_write": 3.75,
        "output":     15.00,
    },
    "claude-opus-4-7": {
        "input":       5.00,
        "cache_read":  0.50,
        "cache_write": 6.25,
        "output":     25.00,
    },
}


def _cost(model: str, usage) -> float:
    p = PRICING[model]
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (
        input_tokens * p["input"]
        + cache_read * p["cache_read"]
        + cache_write * p["cache_write"]
        + output_tokens * p["output"]
    ) / 1_000_000


def log_call(component: str, model: str, usage, run_id: str | None = None) -> float:
    """Append one API call's usage to the ledger and return the dollar cost.

    ``component`` is one of ``"scout-score" | "scout-verdict" | "scout-judge" |
    "lab-classify" | "lab-generate" | "lab-interpret"``. The lab runner's
    daily cap reader looks for entries whose component starts with ``"lab-"``.
    """
    cost = _cost(model, usage)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cost_usd": round(cost, 6),
        "run_id": run_id or os.environ.get("GITHUB_RUN_ID") or str(uuid.uuid4())[:8],
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return cost


def month_to_date_total() -> float:
    """Sum all ``cost_usd`` entries in the current calendar month (UTC)."""
    if not LEDGER.exists():
        return 0.0
    today = datetime.now(timezone.utc)
    prefix = today.strftime("%Y-%m")
    total = 0.0
    with LEDGER.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec["ts"].startswith(prefix):
                    total += rec["cost_usd"]
            except (json.JSONDecodeError, KeyError):
                continue
    return total
