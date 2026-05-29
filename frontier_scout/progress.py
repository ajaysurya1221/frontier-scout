"""Progress reporting abstraction shared by the TUI and the CLI.

v1.3.0 — Mission Control redesign. Backends (``scout.run_scan``,
``dependencies.run_dependency_scan``, ``guard.run_guard``,
``evaluate.evaluate_url``, ``dossier.build_dossier``,
``scripts.lab_runner.run``) accept an optional ``reporter:
ProgressReporter | None = None`` kwarg and emit a small number of
``stage`` / ``advance`` / ``log`` events as they progress.

The TUI fans these events out to a status strip, a progress bar, and
the activity log (``frontier_scout.tui.progress_view``). The CLI
``--progress`` flag attaches a stderr reporter (single ``\r`` line
that's safe in pipelines and CI logs). Default ``None`` is a true
no-op — every existing CLI caller is unaffected.

Why the abstraction lives outside ``tui/``: workers in
``frontier_scout/`` and ``scripts/`` cannot import textual at module
load — the lab runner ships without the textual extra in some
deployments. Keeping the protocol in plain ``frontier_scout.progress``
lets the worker code stay TUI-agnostic while the TUI provides a
concrete implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """Three thin event sinks any backend can fire without crashing.

    Implementations must be **thread-safe** — backends often run inside
    a Textual ``@work(thread=True)`` worker or a subprocess wrapper.
    """

    def stage(self, label: str, *, total_stages: int | None = None) -> None:
        """Announce a new top-level phase, e.g. "Detecting stack".

        ``total_stages`` is optional — when supplied early, sinks can
        render `2/4` style counters. Implementations should clamp the
        running stage counter at ``total_stages`` if exceeded rather
        than crashing.
        """

    def advance(self, fraction: float, message: str = "") -> None:
        """Report intra-stage progress in ``[0.0, 1.0]``.

        ``fraction`` outside the range is clamped by sinks. ``message``
        is an optional one-line description ("3/5 manifests").
        """

    def log(self, message: str, *, tone: str = "info") -> None:
        """Append a free-form line to the activity log.

        ``tone`` is one of the v1.2.1 tone slugs: ``ok``, ``info``,
        ``warn``, ``error``, ``muted``. Sinks colour accordingly.
        """


class NullReporter:
    """Default no-op reporter. Used when callers don't pass one.

    Defined as a concrete class rather than a sentinel so callers can
    do ``reporter = reporter or NullReporter()`` once and then call
    methods unconditionally — no ``if reporter is not None`` noise
    threaded through every backend.
    """

    def stage(self, label: str, *, total_stages: int | None = None) -> None:  # noqa: D401, ARG002
        return None

    def advance(self, fraction: float, message: str = "") -> None:  # noqa: ARG002
        return None

    def log(self, message: str, *, tone: str = "info") -> None:  # noqa: ARG002
        return None


class RecordingReporter:
    """In-memory reporter for tests. Records every event in order.

    Backends that accept a reporter parameter can be unit-tested
    without any TUI / stderr coupling: pass a RecordingReporter and
    assert against ``.events``.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def stage(self, label: str, *, total_stages: int | None = None) -> None:
        self.events.append(("stage", {"label": label, "total_stages": total_stages}))

    def advance(self, fraction: float, message: str = "") -> None:
        self.events.append(
            ("advance", {"fraction": float(fraction), "message": message})
        )

    def log(self, message: str, *, tone: str = "info") -> None:
        self.events.append(("log", {"message": message, "tone": tone}))

    # ------------------------------------------------------------------
    # Test ergonomics
    # ------------------------------------------------------------------

    @property
    def stages(self) -> list[str]:
        """Just the stage labels, in order. Handy for assertions."""

        return [evt[1]["label"] for evt in self.events if evt[0] == "stage"]

    @property
    def logs(self) -> list[str]:
        return [evt[1]["message"] for evt in self.events if evt[0] == "log"]


class StderrReporter:
    """Single-line stderr reporter for CLI ``--progress``.

    Uses a leading ``\r`` so each new stage overwrites the previous on
    interactive terminals, and ``isatty()`` detection so pipelines /
    CI logs get newline-separated lines instead of an unreadable
    carriage-return mash.

    Format: ``[ ●  Querying judge ]`` — short, unambiguous, no ANSI
    colour by default (keep ``--progress`` machine-parseable). Callers
    can pass ``colour=True`` for an interactive flourish.
    """

    def __init__(self, *, stream=None, colour: bool | None = None) -> None:
        import sys

        self._stream = stream if stream is not None else sys.stderr
        self._is_tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._colour = self._is_tty if colour is None else colour
        self._current_stage = ""
        self._stage_idx = 0
        self._total_stages: int | None = None

    def _emit(self, body: str) -> None:
        prefix = "\r" if self._is_tty else ""
        suffix = "" if self._is_tty else "\n"
        try:
            self._stream.write(f"{prefix}{body}{suffix}")
            self._stream.flush()
        except (OSError, ValueError):
            # Broken pipe / closed stream — never crash the worker.
            # StringIO raises ``ValueError`` rather than ``OSError``
            # when closed; treat both as "stream gone, move on".
            pass

    def stage(self, label: str, *, total_stages: int | None = None) -> None:
        self._stage_idx += 1
        if total_stages is not None:
            self._total_stages = total_stages
        self._current_stage = label
        counter = (
            f" [{self._stage_idx}/{self._total_stages}]"
            if self._total_stages
            else ""
        )
        self._emit(f"● {label}{counter}")

    def advance(self, fraction: float, message: str = "") -> None:
        # Clamp + render. Skip if no current stage (defensive — the
        # backend shouldn't, but we don't want to crash).
        if not self._current_stage:
            return
        f = max(0.0, min(1.0, float(fraction)))
        pct = int(round(f * 100))
        body = f"● {self._current_stage} {pct:>3}%"
        if message:
            body += f"  {message}"
        self._emit(body)

    def log(self, message: str, *, tone: str = "info") -> None:  # noqa: ARG002
        # The stderr reporter is a status line, not a log feed. We
        # emit one terminal line per ``log`` call so CI logs still
        # capture the narrative.
        self._emit(message)
        if self._is_tty:
            self._stream.write("\n")
            self._stream.flush()


__all__ = [
    "NullReporter",
    "ProgressReporter",
    "RecordingReporter",
    "StderrReporter",
]
