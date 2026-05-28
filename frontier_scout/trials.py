"""Trial state and adoption receipt helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .evaluate import evaluate_url
from .mcp_audit import classify_mcp_capabilities
from .policy import evaluate_policy, load_policy
from .store import (
    create_trial_run,
    finish_trial_run,
    home_dir,
    save_evaluation,
    save_lab_result,
    save_permission_manifest,
    save_policy_findings,
)


def run_trial(
    tool: str,
    *,
    url: str | None = None,
    dry_run: bool = False,
    stack: dict | None = None,
    repo: Path | str | None = None,
) -> dict[str, Any]:
    """Run or preview a local trial and write a durable receipt.

    Loads the effective policy for ``repo`` (repo → home → DEFAULT_POLICY)
    so that user-edited policy files are honoured. Fixes Codex review
    finding #2.
    """

    source_url = url or _url_from_tool(tool)
    evaluation = evaluate_url(source_url, stack or {})
    if tool and "/" in tool and not tool.startswith("http"):
        evaluation.tool_name = tool
    manifest = evaluation.permission_manifest or classify_mcp_capabilities(
        source_url,
        tool_name=evaluation.tool_name,
        source_url=source_url,
        evidence_source="url",
    )

    tool_id = save_evaluation(evaluation)
    save_permission_manifest(tool_id, manifest)
    trial_id = create_trial_run(tool_id, requested_action="dry-run" if dry_run else "lab")

    if dry_run:
        lab_result: dict[str, Any] = {
            "runtime": _runtime_hint(source_url, evaluation.category),
            "status": "skipped",
            "exit_code": 0,
            "duration_s": 0.0,
            "cost_usd": 0.0,
            "summary": "Dry-run trial; no subprocess executed.",
        }
    else:
        from .lab import run_lab

        exit_code = run_lab(evaluation.tool_name, source_url, dry_run=False)
        lab_result = {
            "runtime": _runtime_hint(source_url, evaluation.category),
            "status": "passed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "duration_s": 0.0,
            "cost_usd": 0.0,
            "summary": "Lab runner completed; inspect transcript for details.",
        }

    save_lab_result(trial_id, lab_result)
    policy = load_policy(Path(str(repo))) if repo is not None else load_policy(None)
    decision = evaluate_policy(evaluation, manifest, lab_result, policy=policy)
    save_policy_findings(tool_id, decision.findings, trial_id=trial_id)
    finish_trial_run(trial_id, status="completed", decision=decision.verdict)

    receipt = render_trial_receipt(
        tool_name=evaluation.tool_name,
        source_url=source_url,
        decision=decision.verdict,
        policy_summary=decision.summary,
        capabilities=manifest.capabilities,
        lab_result=lab_result,
        findings=[f.model_dump() for f in decision.findings],
    )
    receipt_path = _receipt_path(evaluation.tool_name)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(receipt)

    return {
        "trial_id": trial_id,
        "tool_name": evaluation.tool_name,
        "decision": decision.verdict,
        "policy_summary": decision.summary,
        "lab_result": lab_result,
        "receipt_path": str(receipt_path),
    }


def render_trial_receipt(
    *,
    tool_name: str,
    source_url: str,
    decision: str,
    policy_summary: str,
    capabilities: dict[str, str],
    lab_result: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        f"# TRIAL receipt: {tool_name}",
        "",
        f"Source: {source_url}",
        f"Decision: {decision.upper()}",
        f"Policy: {policy_summary}",
        "",
        "## Permission manifest",
        "",
    ]
    for key in sorted(capabilities):
        lines.append(f"- {key}: {capabilities[key]}")
    lines.extend(["", "## Lab result", ""])
    for key in ("status", "runtime", "exit_code", "duration_s", "cost_usd", "summary"):
        if key in lab_result:
            lines.append(f"- {key}: {lab_result[key]}")
    if findings:
        lines.extend(["", "## Policy findings", ""])
        for finding in findings:
            lines.append(
                f"- [{str(finding.get('severity', '')).upper()}] "
                f"{finding.get('rule_id')}: {finding.get('message')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _receipt_path(tool_name: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", tool_name).strip("-").lower() or "tool"
    return home_dir() / "reports" / "trials" / f"{slug}.md"


def _url_from_tool(tool: str) -> str:
    if tool.startswith(("http://", "https://")):
        return tool
    if "/" in tool:
        return f"https://github.com/{tool}"
    return f"https://pypi.org/project/{tool}/"


def _runtime_hint(url: str, category: str) -> str:
    low = url.lower()
    if "huggingface.co" in low:
        return "huggingface"
    if "npmjs.com" in low:
        return "node"
    if category == "model_drop":
        return "huggingface"
    return "python"
