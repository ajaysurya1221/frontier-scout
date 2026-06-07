"""Command line interface for Frontier Scout.

Frontier Scout compiles a typed repo policy into AI coding-agent native controls
(Claude Code first) and verifies in CI that a PR stayed within the approved scope.
It **emits** config and **verifies** evidence — the agent and GitHub Actions do the
enforcing. The CLI is keyless and offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frontier-scout",
        description=(
            "Compile a repo policy into AI coding-agent native controls (Claude Code "
            "first) and verify PRs stay within approved scope. Emits config; the agent "
            "and GitHub Actions enforce it."
        ),
    )
    parser.add_argument("--version", action="version", version=f"frontier-scout {__version__}")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser(
        "doctor", help="Check this repo's Frontier Scout setup (policy, lock, hooks, workflow)."
    )
    doctor.add_argument("--repo", default=".", help="Repository to check.")
    doctor.add_argument("--json", action="store_true", help="Emit JSON.")

    agent_cmd = sub.add_parser(
        "agent",
        help="Compile a repo policy into agent-native controls, verify PRs, and keep an audit trail.",
    )
    agent_sub = agent_cmd.add_subparsers(dest="agent_command")

    agent_scan = agent_sub.add_parser("scan", help="Enumerate repo agent-risk surfaces (static).")
    agent_scan.add_argument("--repo", default=".", help="Repository to scan.")
    agent_scan.add_argument("--json", action="store_true", help="Emit JSON.")
    agent_scan.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any high-risk surface is found.",
    )

    agent_policy = agent_sub.add_parser("policy", help="Generate or explain the agent policy.")
    agent_policy_sub = agent_policy.add_subparsers(dest="agent_policy_command")
    agent_policy_init = agent_policy_sub.add_parser(
        "init", help="Generate a conservative frontier-scout.policy.json from a scan."
    )
    agent_policy_init.add_argument("--repo", default=".", help="Repository to scan and write into.")
    agent_policy_init.add_argument(
        "--path", default=None, help="Policy file path (default: <repo>/frontier-scout.policy.json)."
    )
    agent_policy_init.add_argument("--force", action="store_true", help="Overwrite an existing policy file.")
    agent_policy_explain = agent_policy_sub.add_parser("explain", help="Render the policy in human-readable form.")
    agent_policy_explain.add_argument("--repo", default=".", help="Repository whose policy to explain.")
    agent_policy_explain.add_argument("--policy", default=None, help="Policy file path.")
    agent_policy_explain.add_argument("--json", action="store_true", help="Emit JSON.")

    agent_check = agent_sub.add_parser(
        "check", help="Evaluate a proposed agent task against the policy (executes nothing)."
    )
    agent_check.add_argument("task", help="The proposed agent task text.")
    agent_check.add_argument("--repo", default=".", help="Repository whose policy to use.")
    agent_check.add_argument("--policy", default=None, help="Policy file path.")
    agent_check.add_argument(
        "--changed-files", nargs="*", default=None, help="Paths the task would touch."
    )
    agent_check.add_argument("--json", action="store_true", help="Emit JSON.")

    agent_receipts = agent_sub.add_parser("receipts", help="Inspect local audit receipts.")
    agent_receipts_sub = agent_receipts.add_subparsers(dest="agent_receipts_command")
    agent_receipts_list = agent_receipts_sub.add_parser("list", help="List receipts (newest first).")
    agent_receipts_list.add_argument("--repo", default=".", help="Repository to read receipts from.")
    agent_receipts_list.add_argument("--json", action="store_true", help="Emit JSON.")
    agent_receipts_show = agent_receipts_sub.add_parser("show", help="Show one receipt by id.")
    agent_receipts_show.add_argument("receipt_id", help="Receipt id (with or without .json).")
    agent_receipts_show.add_argument("--repo", default=".", help="Repository to read receipts from.")
    agent_receipts_show.add_argument("--json", action="store_true", help="Emit JSON.")

    agent_export = agent_sub.add_parser(
        "export", help="Emit an advisory policy snippet (a format, not a client)."
    )
    agent_export.add_argument(
        "format", choices=["claude", "agents-md", "pr-checklist"], help="Snippet format."
    )
    agent_export.add_argument("--repo", default=".", help="Repository whose policy to render.")
    agent_export.add_argument("--policy", default=None, help="Policy file path.")
    agent_export.add_argument("--target", default=".", help="Output directory.")

    agent_compile = agent_sub.add_parser(
        "compile",
        help="Compile the policy into Claude Code native controls + a CI verifier "
        "(emits config; Claude Code / GitHub Actions enforce it).",
    )
    agent_compile.add_argument(
        "--target", choices=["claude"], default="claude", help="Compile target (Claude Code only today)."
    )
    agent_compile.add_argument("--repo", default=".", help="Repository root (policy + lock written here).")
    agent_compile.add_argument(
        "--policy", default=None, help="Policy file path (default: <repo>/frontier-scout.policy.json)."
    )
    agent_compile.add_argument(
        "--out", default=None, help="Output dir for .claude/.github/managed config (default: --repo)."
    )

    agent_verify = agent_sub.add_parser(
        "verify-pr",
        help="Verify a PR's receipts + diff stayed within the approved policy scope (fail-closed).",
    )
    agent_verify.add_argument("--repo", default=".", help="Repository root.")
    agent_verify.add_argument("--base", default=None, help="Base git ref to diff against (e.g. origin/main).")
    agent_verify.add_argument("--receipts", default=None, help="Glob of receipt JSON files to verify.")
    agent_verify.add_argument(
        "--advisory", action="store_true", help="Downgrade violations to warnings (always exit 0)."
    )
    agent_verify.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command is None:
        # A bare ``frontier-scout`` prints help.
        parser.print_help()
        return 0

    if args.command == "doctor":
        from .doctor import render_json, render_text, run_doctor

        checks = run_doctor(args.repo)
        if args.json:
            print(render_json(checks))
        else:
            print(render_text(checks), end="")
        return 1 if any(c.status == "fail" for c in checks) else 0

    if args.command == "agent":
        # Lazy-import the agent-firewall package so the CLI stays cheap to load.
        # Nothing here executes an agent task, runs an MCP server, or reaches the
        # network (the only subprocess, in verify-pr, is a read-only ``git diff``).
        from .agent_firewall.compile import compile_claude as agent_compile_claude
        from .agent_firewall.decision import evaluate_task as agent_evaluate_task
        from .agent_firewall.policy import default_policy_path as agent_default_policy_path
        from .agent_firewall.policy import explain_policy as agent_explain_policy
        from .agent_firewall.policy import generate_policy as agent_generate_policy
        from .agent_firewall.policy import load_policy as agent_load_policy
        from .agent_firewall.policy import save_policy as agent_save_policy
        from .agent_firewall.receipts import list_receipts as agent_list_receipts
        from .agent_firewall.receipts import show_receipt as agent_show_receipt
        from .agent_firewall.receipts import write_receipt as agent_write_receipt
        from .agent_firewall.scan import scan_repo as agent_scan_repo
        from .agent_firewall.verify import verify_pr as agent_verify_pr
        from .exporters.policy_snippets import export_policy_snippets as agent_export_snippets

        verb = args.agent_command
        if verb == "scan":
            result = agent_scan_repo(args.repo)
            if args.json:
                print(result.model_dump_json(indent=2))
            else:
                print(f"Static agent-risk scan of {result.repo} (advisory; nothing executed):")
                for surface in result.surfaces:
                    print(f"  [{surface.risk}] {surface.kind}: {surface.path}")
                counts = ", ".join(f"{k}={v}" for k, v in sorted(result.counts.items()))
                print(f"  {len(result.surfaces)} surface(s){' · ' + counts if counts else ''}")
                if result.detected_checks:
                    print(f"  detected checks: {', '.join(result.detected_checks)}")
            if args.strict and any(s.risk == "high" for s in result.surfaces):
                return 1
            return 0
        if verb == "policy":
            pverb = args.agent_policy_command
            if pverb == "init":
                path = args.path or agent_default_policy_path(args.repo)
                if os.path.exists(path) and not args.force:
                    print(f"Policy already exists: {path} (use --force to overwrite).")
                    return 0
                policy = agent_generate_policy(agent_scan_repo(args.repo))
                agent_save_policy(policy, path)
                print(f"Wrote conservative policy: {path}")
                return 0
            if pverb == "explain":
                policy_path = args.policy or agent_default_policy_path(args.repo)
                policy, warnings = agent_load_policy(policy_path)
                if args.json:
                    print(json.dumps(policy.model_dump(), indent=2))
                else:
                    for warning in warnings:
                        print(f"warning: {warning}")
                    print(agent_explain_policy(policy))
                return 0
            parser.error("agent policy requires a subcommand (init | explain)")
            return 2
        if verb == "check":
            policy_path = args.policy or agent_default_policy_path(args.repo)
            policy, warnings = agent_load_policy(policy_path)
            decision = agent_evaluate_task(args.task, policy, changed_files=args.changed_files)
            agent_write_receipt(decision, repo=args.repo, task=args.task, policy_path=policy_path)
            if args.json:
                print(decision.model_dump_json(indent=2))
            else:
                for warning in warnings:
                    print(f"warning: {warning}")
                print(f"verdict: {decision.verdict} (static pre-check — see `agent compile` to enforce)")
                print(decision.summary)
                for reason in decision.reasons:
                    print(f"  [{reason.severity}] {reason.rule_id}: {reason.message}")
                if decision.required_checks:
                    print(f"  required checks: {', '.join(decision.required_checks)}")
            exit_codes = {"allow": 0, "needs_approval": 3, "block": 4}
            return exit_codes.get(decision.verdict, 0)
        if verb == "receipts":
            rverb = args.agent_receipts_command
            if rverb == "list":
                receipts = agent_list_receipts(args.repo)
                if args.json:
                    print(json.dumps(receipts, indent=2))
                else:
                    if not receipts:
                        print("No receipts yet.")
                    for receipt in receipts:
                        print(
                            f"{receipt.get('receipt_id')} · {receipt.get('verdict')} · "
                            f"{receipt.get('timestamp')}"
                        )
                return 0
            if rverb == "show":
                receipt = agent_show_receipt(args.repo, args.receipt_id)
                if receipt is None:
                    print(f"Receipt not found: {args.receipt_id}")
                    return 1
                if args.json:
                    print(json.dumps(receipt, indent=2))
                else:
                    print(f"Receipt {receipt.get('receipt_id')} ({receipt.get('kind')})")
                    print(f"  verdict:   {receipt.get('verdict')}")
                    print(f"  timestamp: {receipt.get('timestamp')}")
                    print(f"  task:      {receipt.get('task_summary')}")
                    branch = receipt.get("git_branch")
                    commit = receipt.get("git_commit")
                    if branch or commit:
                        print(f"  git:       {branch or '?'} @ {commit or '?'}")
                    for reason in receipt.get("reasons", []):
                        print(f"  - [{reason.get('severity')}] {reason.get('rule_id')}: "
                              f"{reason.get('message')}")
                    checks = receipt.get("required_checks") or []
                    if checks:
                        print(f"  required checks: {', '.join(checks)}")
                return 0
            parser.error("agent receipts requires a subcommand (list | show)")
            return 2
        if verb == "export":
            policy_path = args.policy or agent_default_policy_path(args.repo)
            policy, _ = agent_load_policy(policy_path)
            written = agent_export_snippets(policy, args.target, formats=[args.format])
            print("Wrote advisory snippet(s) (emitted, not enforced):")
            for name, out_path in written.items():
                print(f"  {name}: {out_path}")
            if args.format == "claude":
                print(
                    "note: `agent export claude` emits an advisory markdown snippet. For "
                    "enforceable native config (hooks + settings + CI verifier), use "
                    "`agent compile`."
                )
            return 0
        if verb == "compile":
            policy_path = args.policy or agent_default_policy_path(args.repo)
            if os.path.exists(policy_path):
                policy, warnings = agent_load_policy(policy_path)
                for warning in warnings:
                    print(f"warning: {warning}")
            else:
                policy = agent_generate_policy(agent_scan_repo(args.repo))
                print(f"No policy at {policy_path}; generated a conservative one from a static scan.")
            written = agent_compile_claude(policy, repo=args.repo, out_dir=args.out)
            print("Compiled Claude Code controls (Frontier Scout emits; Claude Code / CI enforce):")
            for name, out_path in written.items():
                print(f"  {name}: {out_path}")
            print(
                "Next: commit these, run Claude Code (the hook decides + writes receipts), open a "
                "PR, and the verifier workflow checks receipts against the diff."
            )
            return 0
        if verb == "verify-pr":
            result = agent_verify_pr(
                args.repo, base=args.base, receipts_glob=args.receipts, advisory=args.advisory
            )
            if args.json:
                print(result.model_dump_json(indent=2))
            else:
                for annotation in result.annotations:
                    print(annotation)
                print(result.summary)
                for violation in result.violations:
                    print(f"  violation: {violation}")
                for warning in result.warnings:
                    print(f"  warning: {warning}")
            return 0 if result.ok else 1
        parser.error(
            "agent requires a subcommand "
            "(scan | policy | check | receipts | export | compile | verify-pr)"
        )
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2
