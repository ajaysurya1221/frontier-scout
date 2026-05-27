"""Command line interface for Frontier Scout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .dep_trial import run_dependency_trial
from .dependencies import run_dependency_scan
from .dossier import build_dossier
from .evaluate import evaluate_url
from .guard import format_findings, run_guard
from .lab import run_lab
from .mcp_audit import classify_mcp_capabilities
from .packs import candidate_rows_for_pack
from .platform.incident_change_scout.workflow import run_incident_demo
from .policy import default_policy_toml, evaluate_policy
from .profile import build_scout_profile, export_profile
from .report import load_verdict_file, render_html, write_demo
from .scout import detect_stack, run_scan
from .store import (
    get_pack,
    home_dir,
    init_home,
    latest_scan,
    list_pack_candidates,
    list_packs,
    save_builtin_packs_if_empty,
    save_evaluation,
    save_pack_candidate,
    save_pack_override,
    save_permission_manifest,
    save_policy_findings,
    save_repo_profile,
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

    setup_cmd = sub.add_parser("setup", help="Open the first-run terminal setup mission control.")
    setup_cmd.add_argument("--repo", default=".", help="Repository to inspect for local setup signals.")
    setup_cmd.add_argument("--plain", action="store_true", help="Use stable plain-text setup output.")
    setup_cmd.add_argument("--json", action="store_true", help="Print setup diagnostics as JSON.")
    setup_cmd.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL used only for a short read-only /api/tags probe.",
    )

    profile_cmd = sub.add_parser("profile", help="Build a local Scout Profile for repo-aware recommendations.")
    profile_cmd.add_argument("--repo", default=".", help="Repository to inspect for local signals.")
    profile_cmd.add_argument("--json", action="store_true", help="Print the profile as JSON.")
    profile_cmd.add_argument("--dependencies", action="store_true", help="Include dependency inventory in text output.")
    profile_cmd.add_argument(
        "--write-repo",
        action="store_true",
        help="Also write .frontier-scout/profile.json inside the target repo.",
    )

    demo_cmd = sub.add_parser("demo", help="Generate an offline demo report with no API keys or network calls.")
    demo_cmd.add_argument("--output-dir", default="demo", help="Directory for demo artifacts.")

    scan_cmd = sub.add_parser("scan", help="Run a live scan, or use --dry-run for seeded output.")
    scan_cmd.add_argument("--repo", default=".", help="Repository used for stack-fit detection.")
    scan_cmd.add_argument("--dry-run", action="store_true", help="Use seeded verdicts and avoid network/LLM calls.")
    scan_cmd.add_argument("--no-store", action="store_true", help="Do not persist the scan to SQLite.")
    scan_cmd.add_argument("--json", action="store_true", help="Print the scan payload as JSON.")
    scan_cmd.add_argument("--pack", help="Limit/personalize scan around one Scout Pack slug.")
    scan_cmd.add_argument(
        "--discover",
        action="store_true",
        help="Opt into live/dynamic discovery sources where supported.",
    )

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

    dossier_cmd = sub.add_parser("dossier", help="Explain one tool's local fit, risks, gaps, and next safe step.")
    dossier_cmd.add_argument("target", help="Tool name, GitHub repo, package name, or URL.")
    dossier_cmd.add_argument("--repo", default=".", help="Repository used for personalization.")
    dossier_cmd.add_argument("--json", action="store_true", help="Print the dossier payload as JSON.")
    dossier_cmd.add_argument("--dismiss", action="store_true", help="Suppress this target from future pack reports.")
    dossier_cmd.add_argument("--mute", action="store_true", help="Hide this target for the default snooze window.")
    dossier_cmd.add_argument("--pin", action="store_true", help="Protect this target from pack demotion.")
    dossier_cmd.add_argument("--snooze", help="Custom snooze window such as 30d.")

    packs_cmd = sub.add_parser("packs", help="Inspect and refresh living Scout Packs.")
    packs_sub = packs_cmd.add_subparsers(dest="packs_command")
    packs_sub.add_parser("list", help="List built-in and local Scout Packs.")
    packs_show = packs_sub.add_parser("show", help="Show one Scout Pack definition.")
    packs_show.add_argument("slug", help="Pack slug.")
    packs_refresh = packs_sub.add_parser("refresh", help="Refresh pack candidates.")
    packs_refresh.add_argument(
        "--discover",
        action="store_true",
        help="Opt into live discovery. Without it, seed candidates only.",
    )
    packs_refresh.add_argument("--reset-source", help="Reset one stale source id.")
    packs_candidates = packs_sub.add_parser("candidates", help="List current pack candidates.")
    packs_candidates.add_argument("--pack", help="Filter by pack slug.")

    deps_cmd = sub.add_parser("deps", help="Scan dependency intelligence and create upgrade trials.")
    deps_sub = deps_cmd.add_subparsers(dest="deps_command")
    deps_scan = deps_sub.add_parser("scan", help="Scan repo dependencies for meaningful upgrade findings.")
    deps_scan.add_argument("--repo", default=".", help="Repository to inspect.")
    deps_scan.add_argument("--json", action="store_true", help="Print dependency findings as JSON.")
    deps_trial = deps_sub.add_parser("trial", help="Create a safe dependency-upgrade trial receipt.")
    deps_trial.add_argument("package", help="Package name.")
    deps_trial.add_argument("--from", dest="from_version", required=True, help="Current version.")
    deps_trial.add_argument("--to", dest="to_version", required=True, help="Candidate version.")
    deps_trial.add_argument("--repo", default=".", help="Repository to trial against.")
    deps_trial.add_argument("--dry-run", action="store_true", help="Do not execute tests.")
    deps_trial.add_argument("--json", action="store_true", help="Print trial payload as JSON.")

    trial_cmd = sub.add_parser("trial", help="Create a local try-before-trust trial receipt.")
    trial_cmd.add_argument("tool", help="Tool name or URL.")
    trial_cmd.add_argument("--url", help="Canonical open-source URL for the tool.")
    trial_cmd.add_argument("--repo", default=".", help="Repository used for stack-fit detection.")
    trial_cmd.add_argument("--dry-run", action="store_true", help="Write a receipt without subprocess execution.")
    trial_cmd.add_argument(
        "--sandbox",
        choices=["local", "report-only"],
        help="Sandbox profile. local uses the existing hermetic lab; report-only forces a dry-run receipt.",
    )
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
    incident_demo.add_argument(
        "--corpus",
        default="examples/incident_change_scout/corpus",
        help="Seed corpus directory.",
    )
    incident_demo.add_argument(
        "--ticket",
        default="examples/incident_change_scout/tickets/cache-storm.md",
        help="Incident ticket path.",
    )
    incident_demo.add_argument(
        "--output",
        default=".scratch/incident-demo",
        help="Output directory for answer, trace, audit, and eval.",
    )
    incident_demo.add_argument(
        "--approved",
        action="store_true",
        help="Simulate explicit approval for the high-risk action.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from .tui.runner import run_setup

            return run_setup(repo=Path("."), plain=False, json_output=False, ollama_url="http://localhost:11434")
        parser.print_help()
        return 0
    if args.command == "setup":
        from .tui.runner import run_setup

        return run_setup(
            repo=Path(args.repo),
            plain=args.plain,
            json_output=args.json,
            ollama_url=args.ollama_url,
        )
    if args.command == "init":
        home = init_home()
        stack = detect_stack(Path(args.repo))
        stack_path = home / "stack.json"
        stack_path.write_text(json.dumps(stack, indent=2) + "\n")
        print(f"Frontier Scout home: {home}")
        print(f"Stack profile: {stack_path}")
        print(json.dumps(stack, indent=2))
        return 0
    if args.command == "profile":
        home = init_home()
        profile = build_scout_profile(Path(args.repo))
        save_repo_profile(profile)
        profile_path = home / "profiles" / f"{profile.repo_id}.json"
        export_profile(profile, profile_path)
        repo_profile_path = None
        if args.write_repo:
            repo_profile_path = export_profile(profile, Path(args.repo) / ".frontier-scout" / "profile.json")
        if args.json:
            payload = profile.model_dump()
            payload["profile_path"] = str(profile_path)
            if repo_profile_path:
                payload["repo_profile_path"] = str(repo_profile_path)
            print(json.dumps(payload, indent=2))
        else:
            print(f"Scout profile: {profile_path}")
            if repo_profile_path:
                print(f"Repo export: {repo_profile_path}")
            print(f"languages: {', '.join(profile.languages) or 'unknown'}")
            print(f"frameworks: {', '.join(profile.frameworks) or 'none detected'}")
            print(f"agent configs: {', '.join(profile.agent_configs) or 'none detected'}")
            print(f"risk flags: {', '.join(profile.risk_flags) or 'none'}")
            if args.dependencies:
                print("dependencies:")
                for dep in profile.dependencies:
                    resolved = f" -> {dep.resolved_version}" if dep.resolved_version else ""
                    print(f"- {dep.ecosystem}:{dep.name}{dep.specifier}{resolved} ({dep.manifest_path})")
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
            pack=args.pack,
            discover=args.discover,
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
    if args.command == "dossier":
        for flag_name, override in (
            ("dismiss", "suppress"),
            ("mute", "suppress"),
            ("pin", "pin"),
        ):
            if getattr(args, flag_name, False):
                save_pack_override("*", args.target, override, reason=f"dossier --{flag_name}", expires_at=args.snooze)
        payload = build_dossier(args.target, repo=Path(args.repo))
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"DOSSIER {payload['tool_name']}")
            print(f"verdict: {str(payload['verdict']).upper()}")
            print(f"fit: {payload['fit']}")
            print(f"risk: {payload['risk']}")
            print(f"policy: {payload['policy_summary']}")
            print("unknowns:")
            for gap in payload.get("unknowns") or []:
                print(f"- {gap}")
            print(f"next: {payload['next_safe_step']}")
            print(f"receipt: {payload['receipt_path']}")
        return 0
    if args.command == "packs":
        save_builtin_packs_if_empty()
        if args.packs_command == "list":
            for pack in list_packs():
                definition = pack["definition"]
                print(f"{pack['slug']}: {pack['display_name']} ({len(definition.get('seed_repos') or [])} seeds)")
            return 0
        if args.packs_command == "show":
            pack = get_pack(args.slug)
            if not pack:
                parser.error(f"unknown pack: {args.slug}")
            definition = pack["definition"]
            print(f"{definition['slug']}: {definition['display_name']}")
            print(definition.get("description") or "")
            print("seeds:")
            for repo_name in definition.get("seed_repos") or []:
                print(f"- {repo_name}")
            return 0
        if args.packs_command == "refresh":
            count = 0
            for pack in list_packs():
                from .packs import ScoutPack

                pack_model = ScoutPack(**pack["definition"])
                for candidate in candidate_rows_for_pack(pack_model, discover=args.discover):
                    save_pack_candidate(candidate)
                    count += 1
            suffix = " with live discovery requested" if args.discover else " from seed definitions"
            print(f"Refreshed {count} pack candidates{suffix}.")
            return 0
        if args.packs_command == "candidates":
            candidates = list_pack_candidates(args.pack)
            for candidate in candidates:
                print(f"{candidate['pack_slug']} {candidate['state']} {candidate['tool_name']}")
            return 0
        parser.error("packs requires a subcommand")
        return 2
    if args.command == "deps":
        if args.deps_command == "scan":
            payload = run_dependency_scan(Path(args.repo))
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Dependency scan: {len(payload['findings'])} findings")
                for finding in payload["findings"]:
                    print(
                        f"{finding['verdict'].upper()} {finding['package_name']} "
                        f"{finding['from_version']} -> {finding['to_version']} "
                        f"({finding['classification']})"
                    )
            return 0
        if args.deps_command == "trial":
            result = run_dependency_trial(
                args.package,
                from_version=args.from_version,
                to_version=args.to_version,
                repo=Path(args.repo),
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Dependency trial: {result['tool_name']} {result['from_version']} -> {result['to_version']}")
                print(f"status: {result['lab_result']['status']}")
                print(f"receipt: {result['receipt_path']}")
            return 0
        parser.error("deps requires a subcommand")
        return 2
    if args.command == "trial":
        stack = detect_stack(Path(args.repo))
        dry_run = args.dry_run or args.sandbox == "report-only"
        result = run_trial(args.tool, url=args.url, dry_run=dry_run, stack=stack)
        result["sandbox"] = args.sandbox or ("report-only" if dry_run else "local")
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
