"""Incident tab — run the engineering Scout incident-forensics demo."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static, Switch


class IncidentTab(VerticalScroll):
    """Run the Incident Change Scout demo and surface artifacts."""

    DEFAULT_CSS = """
    IncidentTab .incident-section {
        margin-bottom: 1;
    }

    IncidentTab .incident-title {
        text-style: bold;
        color: #d9f7ff;
        margin-bottom: 1;
    }

    IncidentTab .incident-controls {
        height: 3;
    }

    IncidentTab Button {
        margin-right: 1;
        background: #0d1622;
        color: #d9f7ff;
        border: round #25405c;
    }

    IncidentTab Button:focus {
        border: round #24d6a8;
        color: #24d6a8;
    }

    IncidentTab #incident-artifacts {
        border: round #25405c;
        padding: 1 2;
        background: #0d1622;
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, app_ref) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.app_ref = app_ref
        self._approved = False
        self._last_artifacts: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="incident-section"):
            yield Label("Incident Change Scout — local demo", classes="incident-title")
            yield Static(
                "[#6e8aa1]Runs the engineering vertical against the bundled corpus and "
                "ticket. Writes answer, trace, audit, and eval into .scratch/incident-demo/.[/]",
                markup=True,
            )
            with Horizontal(classes="incident-controls"):
                yield Button("Run incident demo", id="incident-run")
                yield Label("approved:", id="incident-approved-label")
                yield Switch(value=False, id="incident-approved")
        with Vertical(classes="incident-section"):
            yield Label("Latest artifacts", classes="incident-title")
            yield Static(
                "[#6e8aa1]No run yet.[/]", id="incident-artifacts", markup=True
            )
            with Horizontal():
                yield Button("Open answer", id="incident-open-answer", disabled=True)
                yield Button("Open trace", id="incident-open-trace", disabled=True)
                yield Button("Open eval", id="incident-open-eval", disabled=True)

    @on(Switch.Changed, "#incident-approved")
    def _toggle_approved(self, event: Switch.Changed) -> None:
        self._approved = event.value

    @on(Button.Pressed, "#incident-run")
    def _run(self) -> None:
        self.app_ref.log_event(
            f"Running incident demo (approved={self._approved})…", tone="info"
        )
        self._run_worker()

    @work(thread=True, exclusive=True)
    def _run_worker(self) -> None:
        from frontier_scout.platform.incident_change_scout.workflow import run_incident_demo

        summary = run_incident_demo(
            corpus_dir=Path("examples/incident_change_scout/corpus"),
            ticket_path=Path("examples/incident_change_scout/tickets/cache-storm.md"),
            output_dir=Path(".scratch/incident-demo"),
            approved=self._approved,
        )
        self.app_ref.call_from_thread(self._apply_summary, summary)

    def _apply_summary(self, summary: dict) -> None:
        self._last_artifacts = summary
        eval_score = (summary.get("eval") or {}).get("score", "—")
        interrupted = summary.get("interrupted")
        lines = [
            f"[#d9f7ff bold]run id:[/] [#24d6a8]{summary.get('run_id', '—')}[/]",
            f"[#6e8aa1]answer:[/] {summary.get('answer_path', '—')}",
            f"[#6e8aa1]trace: [/] {summary.get('trace_path', '—')}",
            f"[#6e8aa1]audit: [/] {summary.get('audit_path', '—')}",
            f"[#6e8aa1]eval:  [/] {summary.get('eval_path', '—')} (score={eval_score})",
        ]
        if interrupted:
            lines.append("[#e3c26f]approval: interrupted before high-risk action[/]")
        self.query_one("#incident-artifacts", Static).update("\n".join(lines))
        for btn_id in ("incident-open-answer", "incident-open-trace", "incident-open-eval"):
            self.query_one(f"#{btn_id}", Button).disabled = False
        self.app_ref.log_event(
            f"Incident demo run {summary.get('run_id')} · eval={eval_score}",
            tone="ok",
        )

    @on(Button.Pressed, "#incident-open-answer")
    def _open_answer(self) -> None:
        self._open_artifact("answer_path")

    @on(Button.Pressed, "#incident-open-trace")
    def _open_trace(self) -> None:
        self._open_artifact("trace_path")

    @on(Button.Pressed, "#incident-open-eval")
    def _open_eval(self) -> None:
        self._open_artifact("eval_path")

    def _open_artifact(self, key: str) -> None:
        if not self._last_artifacts:
            return
        path = self._last_artifacts.get(key)
        if not path:
            return
        webbrowser.open(f"file://{Path(str(path)).resolve()}")
        self.app_ref.log_event(f"Opened {path}", tone="info")
