"""Local, opt-in usage instrumentation for the sanctioned-pack flow.

**Off by default.** When enabled (``FRONTIER_SCOUT_TELEMETRY=1``), events are appended to a local
JSONL ledger (audit-record shaped) under ``$FRONTIER_SCOUT_HOME`` — and **never sent anywhere**.
This measures the validation funnel (candidates → safety → sanction → export) without violating
the local-first / no-telemetry invariant. Operators export and share their own ledger.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from outputs._text import sanitize_sensitive_text

from .store import home_dir

# The validation funnel, in order.
FUNNEL = (
    "candidates_viewed",
    "safety_viewed",
    "sanctioned",
    "sanction_blocked",
    "unsanctioned",
    "exported",
    "proof_variant_kept",
)

_TRUE = {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    """Telemetry is strictly opt-in via ``FRONTIER_SCOUT_TELEMETRY``."""

    return os.environ.get("FRONTIER_SCOUT_TELEMETRY", "").strip().lower() in _TRUE


def events_path() -> Path:
    return home_dir() / "pack-events.jsonl"


def record_event(event: str, **fields: Any) -> bool:
    """Append one event to the local ledger IF opted in. Returns whether it was recorded.

    Makes **no** network call. String field values are secret-redacted before they touch disk.
    """

    if not is_enabled():
        return False
    record: dict[str, Any] = {"ts": datetime.now(UTC).isoformat(), "event": event}
    for key, value in fields.items():
        record[key] = sanitize_sensitive_text(value) if isinstance(value, str) else value
    path = events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return True


def read_events() -> list[dict[str, Any]]:
    path = events_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize() -> dict[str, Any]:
    """Aggregate the local funnel for ``frontier-scout stats``."""

    events = read_events()
    counts = Counter(e.get("event") for e in events)
    summary: dict[str, Any] = {
        "enabled": is_enabled(),
        "total_events": len(events),
        "by_event": {name: counts.get(name, 0) for name in FUNNEL},
    }
    summary["candidates_viewed"] = counts.get("candidates_viewed", 0)
    summary["sanctioned"] = counts.get("sanctioned", 0)
    summary["blocked"] = counts.get("sanction_blocked", 0)
    summary["exported"] = counts.get("exported", 0)
    return summary
