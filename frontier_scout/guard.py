"""CI/local guard for stored Adoption Firewall evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .policy import PolicyFinding
from .store import list_guard_records


def run_guard(
    repo: Path | str | None = None,
    *,
    strict: bool = False,
    reporter: "ProgressReporter | None" = None,
) -> list[PolicyFinding]:
    """Return deterministic findings from the local evidence ledger.

    Note: the ``evaluations``/``trial_runs`` schema does not yet carry a
    repo column, so guard is currently **ledger-global** even when
    ``repo`` is supplied. The argument is accepted for forward
    compatibility (v1.3 adds a schema migration + repo scoping). For now,
    if you want strictly repo-local CI behaviour, run ``frontier-scout
    setup`` against the repo first so its evidence dominates the ledger.

    ``strict`` upgrades every medium-severity finding to high so that CI
    treats them as failing. Previously this argument was silently
    ignored — fixes Codex review finding #2.

    v1.3.0 — accepts an optional ``reporter`` (see
    ``frontier_scout.progress``). ``None`` is a no-op.
    """

    from frontier_scout.progress import NullReporter

    progress = reporter or NullReporter()
    progress.stage("Loading ledger", total_stages=2)
    records = list_guard_records()
    progress.stage("Applying policy", total_stages=2)
    findings: list[PolicyFinding] = []
    for record in records:
        dangerous = set(record.get("dangerous_flags") or [])
        if not dangerous:
            continue
        if record.get("latest_trial_status") == "completed" and record.get("latest_decision") in {"trial", "adopt"}:
            continue
        base_severity = "high" if dangerous & {"write", "shell", "credential", "unknown"} else "medium"
        severity = "high" if strict and base_severity == "medium" else base_severity
        findings.append(
            PolicyFinding(
                severity=severity,  # type: ignore[arg-type]
                rule_id="trial.required",
                message=(
                    "Stored permission manifest exposes "
                    f"{', '.join(sorted(dangerous))}; run a sandbox trial before adoption."
                ),
                tool_name=str(record.get("tool_name") or ""),
            )
        )
    progress.log(f"Guard finished: {len(findings)} finding(s)", tone="ok")
    return findings


def format_findings(
    findings: list[PolicyFinding | dict[str, Any]],
    *,
    output_format: str = "text",
) -> str:
    normalized = [_as_dict(f) for f in findings]
    status = "failed" if normalized else "passed"
    if output_format == "json":
        return json.dumps({"status": status, "findings": normalized}, indent=2)
    if output_format == "github":
        if not normalized:
            return "Frontier Scout Guard: passed"
        lines = []
        for f in normalized:
            lines.append(
                f"::warning title={f.get('rule_id')}::"
                f"{f.get('tool_name')}: {f.get('message')}"
            )
        return "\n".join(lines)

    if not normalized:
        return "Frontier Scout Guard: passed"
    lines = ["Frontier Scout Guard: failed", ""]
    for f in normalized:
        lines.append(f"[{str(f.get('severity', '')).upper()}] {f.get('message')}")
    return "\n".join(lines)


def _as_dict(finding: PolicyFinding | dict[str, Any]) -> dict[str, Any]:
    if isinstance(finding, PolicyFinding):
        return finding.model_dump()
    return dict(finding)
