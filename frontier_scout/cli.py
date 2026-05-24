"""Command line interface for Frontier Scout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .lab import run_lab
from .report import load_verdict_file, render_html, write_demo, write_report
from .scout import detect_stack, run_scan
from .store import home_dir, init_home, latest_scan


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
    parser.error(f"unknown command: {args.command}")
    return 2

