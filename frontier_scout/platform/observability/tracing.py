"""Small local span recorder with OpenTelemetry-shaped fields."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..core.ids import utc_now


class SpanRecord(BaseModel):
    run_id: str
    trace_id: str
    name: str
    kind: str = "internal"
    start_time: str = Field(default_factory=utc_now)
    end_time: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"


class SpanRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def span(self, *, run_id: str, trace_id: str, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        record = SpanRecord(run_id=run_id, trace_id=trace_id, name=name, attributes=attributes)
        try:
            yield record
        except Exception:
            record.status = "error"
            raise
        finally:
            record.end_time = utc_now()
            with self.path.open("a") as f:
                f.write(json.dumps(record.model_dump(), sort_keys=True) + "\n")
