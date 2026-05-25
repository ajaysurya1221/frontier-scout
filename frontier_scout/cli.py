"""Command line interface for Frontier Scout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .evaluate import evaluate_url
from .guard import format_findings, run_guard
from .lab import run_lab
from .mcp_audit import classify_mcp_capabilities
from .platform.incident_change_scout.workflow import run_incident_demo
from .policy import default_policy_toml, evaluate_policy
from .report import load_verdict_file, render_html, write_demo, write_report
from .scout import detect_stack, run_scan
from .store import (
    home_dir,
    init_home,
    latest_scan,
    save_evaluation,
    save_permission_manifest,
    save_policy_findings,
)
from .trials import run_trial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frontier-scout",
        description="Local AI adoption radar for tools, MCP servers, agent frameworks, and model drops.",
    )
    parser.add_argument("--version", action="version", version=f"frontier-scout {__version__}")
    sub = parser.add_subparsers(dest="command")

    init_cmd = sub.add_parser("init", help="Create the local Frontier Scout home and print detected stack signals.")
    init_cmd.add_argument("--repo", default=".", help="Repository to inspect for stack signals.")

    demo_cmd = sub.add_parser("demo", help="Generate an offline demo report with no API keys or network calls.")
    demo_cmd.add_argument("--output-dir", default="demo", help="Directory for demo artifacts.")

    scan_cmd = sub.add_parser("scan", help="Run a live scan, or use --dry-run for seeded output.")
    scan_cmd.add_argument("--repo", default=".", help="Repository used for stack-fit detection.")
    scan_cmd.add_argument("--dry-run", action="store_true", help="Use seeded verdicts and avoid network/LLM calls.")
    scan_cmd.add_argument("--no-store", action="store_true", help="Do not persist the scan to SQLite.")
    scan_cmd.add_argument("--json", action="store_true", help="Print the scan payload as JSON.")

    report_cmd = sub.add_parser("report", help="Render a static HTML report from a verdict JSON file or latest scan.")
    report_cmd.add_argument("--input", help="Path to verdict JSON. Defaults to latest SQLite scan, then demo fixture.")
    report_cmd.add_argument("--output", default="demo/briefing.html", help="HTML output path.")

    lab_cmd = sub.add_parser("lab", help="Try a tool in the hermetic polyglot lab.")
    lab_cmd.add_argument("tool", help="Tool/package name.")
    lab_cmd.add_argument("--url", required=True, help="Open-source URL for the tool.")
    lab_cmd.add_argument("--dry-run", action="store_true", help="Classify/preview without subprocess execution.")

    eval_cmd = sub.add_parser("evaluate", help="Evaluate one AI tool URL before trial or adoption.")
    eval_cmd.add_argument("url", help="GitHub, PyPI, npm, Hugging Face, MCP, or vendor URL.")
    eval_cmd.add_argument("--repo", default=".", help="Repository used for stack-fit detection.")
    eval_cmd.add_argument("--json", action="store_true", help="Print the evaluation payload as JSON.")

    trial_cmd = sub.add_parser("trial", help="Create a local try-before-trust trial receipt.")
    trial_cmd.add_argument("tool", help="Tool name or URL.")
    trial_cmd.add_argument("--url", help="Canonical open-source URL for the tool.")
    trial_cmd.add_argument("--repo", default=".", help="Repository used for stack-fit detection.")
    trial_cmd.add_argument("--dry-run", action="store_true", help="Write a receipt without subprocess execution.")
    trial_cmd.add_argument("--json", action="store_true", help="Print the trial payload as JSON.")

    guard_cmd = sub.add_parser("guard", help="Run deterministic local adoption policy checks.")
    guard_cmd.add_argument("--repo", default=".", help="Repository to inspect for local policy.")
    guard_cmd.add_argument(
        "--format",
        choices=["text", "json", "github"],
        default="text",
        help="Output format.",
    )
    guard_cmd.add_argument("--strict", action="store_true", help="Exit non-zero on medium findings too.")

    policy_cmd = sub.add_parser("policy", help="Manage local Adoption Firewall policy.")
    policy_sub = policy_cmd.add_subparsers(dest="policy_command")
    policy_init = policy_sub.add_parser("init", help="Write a conservative default policy file.")
    policy_init.add_argument("--home-only", action="store_true", help="Write to ~/.frontier-scout/policy.toml.")
    policy_init.add_argument("--repo", default=".", help="Repository for .frontier-scout/policy.toml.")

    incident_cmd = sub.add_parser("incident", help="Run the Engineering Scout incident-forensics vertical slice.")
    incident_sub = incident_cmd.add_subparsers(dest="incident_command")
    incident_demo = incident_sub.add_parser("demo", help="Run the local Incident Change Scout demo.")
    incident_demo.add_argument("--corpus", default="examples/incident_change_scout/corpus", help="Seed corpus directory.")
    incident_demo.add_argument("--ticket", default="examples/incident_change_scout/tickets/cache-storm.md", help="Incident ticket path.")
    incident_demo.add_argument("--output", default=".scratch/incident-demo", help="Output directory for answer, trace, audit, and eval.")
    incident_demo.add_argument("--approved", action="store_true", help="Simulate explicit approval for the high-risk action.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "init":
        home = init_home()
        stack = detect_stack(Path(args.repo))
        stack_path = home / "stack.json"
        stack_path.write_text(json.dumps(stack, indent=2) + "\n")
        print(f"Frontier Scout home: {home}")
        print(f"Stack profile: {stack_path}")
        print(json.dumps(stack, indent=2))
        return 0
    if args.command == "demo":
        paths = write_demo(Path(args.output_dir))
        print(f"Wrote HTML report: {paths['html']}")
        print(f"Wrote verdict data: {paths['json']}")
        return 0
    if args.command == "scan":
        payload = run_scan(
            repo=Path(args.repo),
            dry_run=args.dry_run,
            persist=not args.no_store,
        )
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"Scan complete: {len(payload.get('verdicts', []))} verdicts, "
                f"${float(payload.get('cost_usd', 0)):.4f}, home={home_dir()}"
            )
        return 0
    if args.command == "report":
        if args.input:
            date, verdicts, funnel = load_verdict_file(Path(args.input))
        else:
            payload = latest_scan()
            if payload is None:
                paths = write_demo(Path(args.output).parent)
                print(f"No stored scan found; wrote demo report: {paths['html']}")
                return 0
            date = str(payload.get("date") or "latest")
            verdicts = list(payload.get("verdicts") or [])
            funnel = payload
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_html(verdicts, date=date, funnel=funnel))
        print(f"Wrote HTML report: {output}")
        return 0
    if args.command == "lab":
        return run_lab(args.tool, args.url, dry_run=args.dry_run)
    if args.command == "evaluate":
        stack = detect_stack(Path(args.repo))
        evaluation = evaluate_url(args.url, stack)
        tool_id = save_evaluation(evaluation)
        manifest = evaluation.permission_manifest or classify_mcp_capabilities(
            args.url,
            tool_name=evaluation.tool_name,
            source_url=args.url,
        )
        save_permission_manifest(tool_id, manifest)
        decision = evaluate_policy(evaluation, manifest)
        save_policy_findings(tool_id, decision.findings)
        if args.json:
            print(
                json.dumps(
                    {
                        "evaluation": evaluation.model_dump(),
                        "policy": decision.model_dump(),
                    },
                    indent=2,
                )
            )
        else:
            caps = " ".join(
                f"{k}={v}"
                for k, v in sorted(manifest.capabilities.items())
                if v != "unlikely"
            )
            print(f"EVALUATE {evaluation.tool_name}")
            print(f"category: {evaluation.category}")
            print(f"fit: {evaluation.fit}")
            print(f"risk: {evaluation.risk}")
            print(f"capabilities: {caps or 'none detected'}")
            print(f"policy: {decision.summary}")
            print(f"next: frontier-scout trial {evaluation.tool_name} --url {evaluation.source_url} --dry-run")
        return 0
    if args.command == "trial":
        stack = detect_stack(Path(args.repo))
        result = run_trial(args.tool, url=args.url, dry_run=args.dry_run, stack=stack)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            lab_result = result.get("lab_result") or {}
            print(f"TRIAL {result['tool_name']}")
            print(f"runtime: {lab_result.get('runtime', 'unknown')}")
            print(f"lab: {lab_result.get('status', 'unknown')}")
            print(f"cost: ${float(lab_result.get('cost_usd') or 0):.3f}")
            print(f"policy: {result['policy_summary']}")
            print(f"receipt: {result['receipt_path']}")
        return 0
    if args.command == "guard":
        findings = run_guard(Path(args.repo), strict=args.strict)
        print(format_findings(findings, output_format=args.format))
        if any(f.severity == "high" or (args.strict and f.severity == "medium") for f in findings):
            return 1
        return 0
    if args.command == "policy":
        if args.policy_command == "init":
            if args.home_only:
                path = init_home() / "policy.toml"
            else:
                path = Path(args.repo) / ".frontier-scout" / "policy.toml"
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_policy_toml())
            print(f"Wrote policy: {path}")
            return 0
        parser.error("policy requires a subcommand")
        return 2
    if args.command == "incident":
        if args.incident_command == "demo":
            summary = run_incident_demo(
                corpus_dir=Path(args.corpus),
                ticket_path=Path(args.ticket),
                output_dir=Path(args.output),
                approved=args.approved,
            )
            print(f"Incident demo run: {summary['run_id']}")
            print(f"answer: {summary['answer_path']}")
            print(f"trace: {summary['trace_path']}")
            print(f"audit: {summary['audit_path']}")
            print(f"eval: {summary['eval_path']} score={summary['eval']['score']}")
            if summary["interrupted"]:
                print("approval: interrupted before high-risk action")
            return 0
        parser.error("incident requires a subcommand")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2
