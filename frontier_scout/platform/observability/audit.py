"""Cloudflare-style JSONL audit records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..core.ids import utc_now


class AuditRecord(BaseModel):
    run_id: str
    trace_id: str
    actor: str
    operation: str
    resource_type: str
    resource_id: str
    timestamp: str = Field(default_factory=utc_now)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    decision: str = "allow"
    provenance: list[str] = Field(default_factory=list)


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: AuditRecord) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(record.model_dump(), sort_keys=True) + "\n")

