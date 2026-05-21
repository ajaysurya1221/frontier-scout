"""
Centralized Anthropic client with bounded exponential backoff + jitter.

Every LLM call in the system routes through `call_with_retry()` so retry
behavior is consistent across Scout score / Scout verdict / Pulse score /
Pulse verdict / Judge / Synthesizer. The reviewer's final audit flagged a
production-blocking Opus 529 OverloadedError that aborted a Scout run mid-way;
this module fixes that by retrying:

  - 529 OverloadedError  (provider-wide overload)
  - 5xx server errors    (provider-side transient)
  - 408 / 429            (rate limit / request timeout)
  - APIConnectionError   (network / TLS / DNS)
  - APITimeoutError      (httpx timeout)

Backoff: 1s, 4s, 12s, 30s (cap), with ±25% jitter. 4 retries total → max ~50s
extra latency. Total cost cap: still bounded by Anthropic monthly limit.

Each retry logs to stderr (visible in GitHub Actions logs) AND increments
a counter that the caller can include in its `quality-log.jsonl` row.
"""

from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

# Configurable via env so we can dial back without a code change.
MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "4"))
BASE_DELAY = float(os.environ.get("LLM_BASE_DELAY", "1.0"))
MAX_DELAY = float(os.environ.get("LLM_MAX_DELAY", "30.0"))

# Anthropic SDK exception classes that we know are transient.
_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


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


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, _RETRY_EXCEPTIONS):
        return True
    # APIStatusError covers 4xx/5xx; retry on 408/429/5xx.
    if isinstance(exc, anthropic.APIStatusError):
        code = getattr(exc, "status_code", None)
        if code in {408, 409, 429, 529} or (isinstance(code, int) and 500 <= code < 600):
            return True
    return False


def _delay(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt=0 is the first retry."""
    base = min(MAX_DELAY, BASE_DELAY * (3 ** attempt))
    jitter = random.uniform(-0.25, 0.25) * base
    return max(0.1, base + jitter)


def call_with_retry(
    client: anthropic.Anthropic,
    component: str,
    **create_kwargs: Any,
) -> Any:
    """
    Wrap `client.messages.create(**create_kwargs)` with retry/backoff.

    `component` is a human-readable tag ("scout-score", "scout-verdict",
    "scout-judge", "pulse-score", "pulse-verdict", "synth") used in retry
    logs and the per-component stats dict.

    Raises the last exception if all retries are exhausted.
    """
    attempts = MAX_RETRIES + 1  # first try + retries
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return client.messages.create(**create_kwargs)
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if i >= MAX_RETRIES or not _should_retry(exc):
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
