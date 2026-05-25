"""Stable identifiers used across runs, traces, and citations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime


def stable_id(prefix: str, *parts: object) -> str:
    """Return a deterministic short ID for stable demo artifacts."""

    raw = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def utc_now() -> str:
    """ISO timestamp in UTC, suitable for audit records."""

    return datetime.now(UTC).isoformat()
