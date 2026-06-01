"""Thread-safe messages the Mission Control workers post back to the app."""

from __future__ import annotations

from typing import Any

from textual.message import Message


class Progress(Message):
    """A staged-progress update from a running worker."""

    def __init__(self, kind: str, text: str) -> None:
        super().__init__()
        self.kind = kind
        self.text = text


class WorkDone(Message):
    """A worker finished successfully with a payload."""

    def __init__(self, kind: str, payload: Any) -> None:
        super().__init__()
        self.kind = kind
        self.payload = payload


class WorkFailed(Message):
    """A worker raised; carry the error text for an error toast/screen."""

    def __init__(self, kind: str, error: str) -> None:
        super().__init__()
        self.kind = kind
        self.error = error


class TuiReporter:
    """A ProgressReporter that posts Progress messages to the app (thread-safe)."""

    def __init__(self, app: Any, kind: str) -> None:
        self._app = app
        self._kind = kind

    def stage(self, label: str, total_stages: int | None = None) -> None:
        self._post(label)

    def advance(self, fraction: float, message: str = "") -> None:
        if message:
            self._post(message)

    def log(self, message: str, tone: str = "info") -> None:
        self._post(message)

    def _post(self, text: str) -> None:
        try:
            self._app.call_from_thread(self._app.post_message, Progress(self._kind, text))
        except Exception:  # noqa: BLE001
            try:
                self._app.post_message(Progress(self._kind, text))
            except Exception:  # noqa: BLE001
                pass
