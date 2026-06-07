"""Policy lock: bind compiled artifacts and receipts to an exact policy.

The lock is a small JSON file (``policy.lock.json``) holding the sha256 of the
policy that was compiled, the Frontier Scout version, a compile timestamp, and
the targets compiled for. The native hook stamps the same hash into every action
receipt; the PR verifier rejects receipts whose hash drifts from the lock (stale
or out-of-band policy edits). This is a content hash, **not** a signed ledger —
P1 may wrap it with existing attestation tooling.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frontier_scout import __version__

from .models import AgentPolicy

__all__ = ["policy_hash", "default_lock_path", "write_lock", "read_lock", "LOCK_FILENAME"]

LOCK_FILENAME = "policy.lock.json"


def policy_hash(policy: AgentPolicy | dict[str, Any]) -> str:
    """Return the sha256 of ``policy`` over a canonical (sorted, compact) JSON form.

    Order-independent: a model and its ``model_dump()`` round-trip hash identically.
    """

    data = policy.model_dump() if isinstance(policy, AgentPolicy) else dict(policy)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_lock_path(repo: str) -> str:
    """Return ``<repo>/policy.lock.json`` (sits beside the policy file)."""

    return os.path.join(repo, LOCK_FILENAME)


def write_lock(policy: AgentPolicy | dict[str, Any], repo: str, *, targets: list[str]) -> str:
    """Write the lock for ``policy`` into ``repo``; return the path written."""

    path = default_lock_path(repo)
    lock = {
        "policy_sha256": policy_hash(policy),
        "frontier_scout_version": __version__,
        "compiled_at": datetime.now(UTC).isoformat(),
        "targets": list(targets),
    }
    Path(path).write_text(json.dumps(lock, indent=2) + "\n")
    return path


def read_lock(path: str) -> dict[str, Any] | None:
    """Load a lock file; ``None`` if missing or unparseable."""

    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
