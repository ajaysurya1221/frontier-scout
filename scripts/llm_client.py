"""
Centralized Anthropic client with bounded exponential backoff + jitter.

Every LLM call in the system routes through `call_with_retry()` so retry
behavior is consistent across Scout score, Scout verdict, judge, and lab
interpretation paths. A prior live run hit a provider-side Opus 529
OverloadedError mid-scan; this module fixes that by retrying:

  - 529 OverloadedError  (provider-wide overload)
  - 5xx server errors    (provider-side transient)
  - 408 / 429            (rate limit / request timeout)
  - APIConnectionError   (network / TLS / DNS)
  - APITimeoutError      (httpx timeout)

Backoff: 1s, 4s, 12s, 30s (cap), with ±25% jitter. 4 retries total → max ~50s
extra latency. Total cost cap: still bounded by Anthropic monthly limit.

Each retry logs to stderr (visible in GitHub Actions workflow logs) AND increments
a counter that the caller can include in its `quality-log.jsonl` row.
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Configurable via env so we can dial back without a code change.
MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "4"))
BASE_DELAY = float(os.environ.get("LLM_BASE_DELAY", "1.0"))
MAX_DELAY = float(os.environ.get("LLM_MAX_DELAY", "30.0"))


@dataclass
class RetryStats:
    """Tracks retry behavior across calls within one pipeline run."""
    total_retries: int = 0
    last_error: str | None = None
    by_component: dict[str, int] = field(default_factory=dict)

    def record(self, component: str, error: str) -> None:
        self.total_retries += 1
        self.last_error = error
        self.by_component[component] = self.by_component.get(component, 0) + 1


# Module-level singleton; pipeline scripts import and read at log time.
STATS = RetryStats()


def _delay(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt=0 is the first retry."""
    base = min(MAX_DELAY, BASE_DELAY * (3 ** attempt))
    jitter = random.uniform(-0.25, 0.25) * base
    return max(0.1, base + jitter)


def call_with_retry(
    provider: Any,
    component: str,
    **create_kwargs: Any,
) -> Any:
    """
    Wrap ``provider.create(**create_kwargs)`` with retry/backoff.

    ``provider`` is an :class:`frontier_scout.providers.LLMProvider` (any
    backend — Anthropic, OpenAI, or a CLI). Whether an exception is
    transient is delegated to ``provider.is_retryable`` so each backend
    owns its own error taxonomy.

    `component` is a human-readable tag ("scout-score", "scout-verdict",
    "scout-judge", "lab-classify", …) used in retry logs and the
    per-component stats dict.

    Raises the last exception if all retries are exhausted.
    """
    attempts = MAX_RETRIES + 1  # first try + retries
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return provider.create(**create_kwargs)
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if i >= MAX_RETRIES or not provider.is_retryable(exc):
                # Either out of retries or this is a non-retryable error
                raise
            wait = _delay(i)
            STATS.record(component, type(exc).__name__)
            print(
                f"  ⚠️  [{component}] {type(exc).__name__}: {exc!s}"
                f"  → retry {i+1}/{MAX_RETRIES} in {wait:.1f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)
    # Unreachable, but mypy/pyright happy
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("call_with_retry exited without result or exception")
