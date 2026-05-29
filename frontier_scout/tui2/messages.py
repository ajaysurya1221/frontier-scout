"""Textual messages — the only channel between worker threads and the UI.

All async work follows one rule: a worker emits live ``Progress`` events and
exactly one terminal message, ``WorkDone`` or ``WorkFailed``. Both are
marshaled to the UI thread via ``post_message``; the UI thread never blocks and
never touches worker memory. Because every worker ends in one of the two
terminal messages, **every flow is a total function** — it always lands on a
result screen or an error screen, never a frozen wait.
"""

from __future__ import annotations

from typing import Any

from textual.message import Message


class Progress(Message):
    """A staged-progress update from a running worker."""

    def __init__(self, stage: str, *, done: bool = False, tone: str = "info") -> None:
        self.stage = stage
        self.done = done  # True once this stage is finished (renders a ✓)
        self.tone = tone
        super().__init__()


class WorkDone(Message):
    """A worker finished successfully. ``payload`` is flow-specific."""

    def __init__(self, kind: str, payload: Any) -> None:
        self.kind = kind  # "scout" | "explore" | "implement" | "lab" | "evaluate"
        self.payload = payload
        super().__init__()


class WorkFailed(Message):
    """A worker raised. ``error`` is a human-readable message, never a traceback."""

    def __init__(self, kind: str, error: str, *, suggestion: str = "") -> None:
        self.kind = kind
        self.error = error
        self.suggestion = suggestion
        super().__init__()
