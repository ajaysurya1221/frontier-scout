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
import sys
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
# Anthropic verified 2026-05-20; OpenAI verified 2026-05-29 (list price).
# CLI backends (claude-code-cli / codex-cli) are $0 marginal — the
# subscription absorbs the tokens — so they map to all-zero entries.
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
    "gpt-4o": {
        "input":       2.50,
        "cache_read":  1.25,
        "cache_write": 2.50,
        "output":     10.00,
    },
    "gpt-4o-mini": {
        "input":       0.15,
        "cache_read":  0.075,
        "cache_write": 0.15,
        "output":      0.60,
    },
    "claude-code-cli": {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0},
    "codex-cli": {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0},
}


# Conservative fallback for a model id we don't have list prices for. We take
# the *most expensive* rate across every known paid model so an unknown id can
# never UNDER-count spend and silently slip past a budget cap. Over-counting is
# the safe failure mode for a guard. CLI ($0) backends are explicit entries in
# PRICING, so they never hit this fallback.
def _conservative_rates() -> dict[str, float]:
    paid = [p for p in PRICING.values() if any(v > 0 for v in p.values())]
    keys = ("input", "cache_read", "cache_write", "output")
    return {k: max(p.get(k, 0.0) for p in paid) for k in keys}


_FALLBACK_RATES = _conservative_rates()
_warned_models: set[str] = set()


def _resolve_pricing(model: str) -> dict[str, float] | None:
    """Look up a model's rate table, tolerating dated suffixes.

    Providers may echo a dated id (``claude-sonnet-4-6-20251001``) for an alias
    we price under its base name (``claude-sonnet-4-6``). Try an exact match
    first, then the longest known key that is a prefix of ``model``.
    """
    exact = PRICING.get(model)
    if exact is not None:
        return exact
    candidates = [k for k in PRICING if model.startswith(k)]
    if candidates:
        return PRICING[max(candidates, key=len)]
    return None


def _cost(model: str, usage) -> float:
    # An unknown model (e.g. a future provider id) must NOT cost $0 — that would
    # silently bypass the budget cap on the user's own key. Instead apply the
    # most-expensive known rate and warn once, so caps trigger conservatively.
    p = _resolve_pricing(model)
    if p is None:
        if model not in _warned_models:
            _warned_models.add(model)
            print(
                f"⚠️  cost_tracker: unknown model {model!r} — using conservative "
                "(max known) pricing for budget safety. Add it to PRICING to "
                "get exact cost.",
                file=sys.stderr,
            )
        p = _FALLBACK_RATES
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (
        input_tokens * p.get("input", 0.0)
        + cache_read * p.get("cache_read", 0.0)
        + cache_write * p.get("cache_write", 0.0)
        + output_tokens * p.get("output", 0.0)
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
