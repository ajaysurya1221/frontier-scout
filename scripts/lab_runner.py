#!/usr/bin/env python3
"""
Frontier Scout — Lab Runner (Round 7, Phase A).

When a teammate clicks 🧪 Run Lab on a verdict card in Slack, the Lambda
triggers the `lab-from-slack` GitHub Actions workflow, which invokes this script.

What the lab does (one click → one Slack reply, ~5–10 min):

  1. Classify the tool (1 Sonnet call) — {vector_db, llm_framework, …}
  2. Generate a stack-shaped synthetic test script (1 Sonnet call)
     using the existing `cached_system_blocks` knowledge of the team stack
     (FastAPI + LangGraph + Anthropic + Python 3.11)
  3. Safety-scan the script for secret-leak patterns; abort if found
  4. Subprocess `pip install <tool>` then run the test with env={} +
     PATH + HOME ONLY. The child process literally cannot call any paid
     API because it has no key. 3-min wall-clock timeout.
  5. Interpret the captured stdout/stderr/exit_code (1 Sonnet call)
  6. Post a threaded reply on the original verdict card (found via the
     briefings/<date>-meta.json map written by Round 6's threaded poster)
  7. Commit a full transcript to .scratch/labs/<date>-<tool>.md

Cost guardrails (all in this file, all overridable via env):

  LAB_RUNS_PER_DAY=1          — caps lab clicks per UTC day
  LAB_DAILY_USD_CAP=1.00      — reads costs.jsonl, refuses if today >= cap
  LAB_SUBPROCESS_TIMEOUT=180  — 3-minute wall clock on the child process
  LAB_MAX_TOKENS=2000         — per Sonnet call

If either cap fires the lab posts a polite refusal instead of running.

Trust boundary:

  • subprocess.run(env={...minimal...}) — no application secret reaches the
    generated script.
  • Synthetic-only generator prompt + a SECRET_LEAK_RE pre-check before
    execution.
  • Output is read-only: thread reply + .scratch/labs/ artifact only.
    The lab never modifies application repositories or pushes a PR.

Usage:

  python scripts/lab_runner.py --tool dspy \\
      --url https://github.com/stanfordnlp/dspy --user U123456

  # Dry-run (no subprocess, no Slack call, no committed artifact):
  DRY_RUN=1 python scripts/lab_runner.py --tool dspy \\
      --url https://github.com/stanfordnlp/dspy
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from cost_tracker import log_call
from llm_client import call_with_retry
from prompts import STACK

REPO_ROOT = Path(__file__).parent.parent
LABS_DIR = REPO_ROOT / ".scratch" / "labs"
BRIEFINGS_DIR = REPO_ROOT / "briefings"
COSTS_LEDGER = REPO_ROOT / "costs.jsonl"

MODEL = "claude-sonnet-4-6"

# ── Cost & safety guardrails ─────────────────────────────────────────────────
#
# Defaults are sized for normal team usage, not "demo at all costs."
# Override via GitHub Actions variables/secrets if traffic patterns change.
#
#   LAB_RUNS_PER_DAY=10        — daily click count cap (per UTC day)
#   LAB_DAILY_USD_CAP=5.00     — daily USD ceiling across all `lab-*` cost entries
#   LAB_SUBPROCESS_TIMEOUT=600 — 10-min wall clock per subprocess step;
#                                applies separately to install + run, so
#                                the total wall-clock worst case is 20 min.
#                                Covers heavy ML installs (torch, transformers)
#                                without setting wildly optimistic expectations.
#   LAB_MAX_TOKENS=3000        — per Sonnet call output cap
#
LAB_RUNS_PER_DAY = int(os.environ.get("LAB_RUNS_PER_DAY", "10"))
LAB_DAILY_USD_CAP = float(os.environ.get("LAB_DAILY_USD_CAP", "5.00"))
SUBPROCESS_TIMEOUT = int(os.environ.get("LAB_SUBPROCESS_TIMEOUT", "600"))  # seconds
MAX_TOKENS_PER_CALL = int(os.environ.get("LAB_MAX_TOKENS", "3000"))

# Only labs on real open-source URLs. Closed-source tools shouldn't even
# have the button surfaced; this is the second line of defence.
OPEN_SOURCE_URL_RE = re.compile(
    r"^https?://(www\.)?(github\.com|pypi\.org|huggingface\.co|gitlab\.com)/",
    re.IGNORECASE,
)

# If Sonnet ever emits one of these in the generated test script, refuse to
# execute. Belt-and-braces against prompt injection that tries to bake real
# secrets into the script.
SECRET_LEAK_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{20,}"
    r"|sk-proj-[A-Za-z0-9_-]{20,}"
    r"|xoxb-[A-Za-z0-9_-]{20,}"
    r"|xoxa-[A-Za-z0-9_-]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|ASIA[A-Z0-9]{12,}"
    r"|AKIA[A-Z0-9]{12,})",
)


# ── Public entry points ──────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Frontier Scout lab runner")
    parser.add_argument("--tool", required=True, help="Tool name as it appears on the verdict card")
    parser.add_argument("--url", required=True, help="Open-source source URL")
    parser.add_argument("--user", default="", help="Slack username who clicked 🧪")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip subprocess + Slack call; print classification/script/would-be-reply only",
    )
    args = parser.parse_args()
    return run(tool=args.tool, url=args.url, user=args.user, dry_run=args.dry_run)


def run(tool: str, url: str, user: str = "", dry_run: bool | None = None) -> int:
    """Orchestrate one lab. Returns shell-style exit code (0 = success or
    polite refusal; 1 = hard error caller should surface)."""
    dry_run = bool(dry_run) if dry_run is not None else (os.environ.get("DRY_RUN") == "1")
    print(f"🧪 Lab runner — tool={tool!r} url={url!r} dry_run={dry_run}")

    # 0. URL gate — should already be enforced upstream, but double-check.
    if not OPEN_SOURCE_URL_RE.match(url or ""):
        msg = (
            f":no_entry_sign: *Lab declined for {tool}* — `{url}` doesn't look "
            f"like an open-source repo URL (github.com / pypi.org / huggingface.co / gitlab.com)."
        )
        print(msg)
        _post_thread_if_possible(tool, msg, dry_run=dry_run)
        return 0

    # 0b. Cost & frequency caps (only enforced for real runs).
    if not dry_run:
        refusal = _within_caps()
        if refusal is not None:
            print(refusal)
            _post_thread_if_possible(tool, refusal, dry_run=False)
            return 0

    client = _anthropic_client() if not dry_run or os.environ.get("ANTHROPIC_API_KEY") else None

    # 1. Resolve tool (deterministic — README + PyPI metadata if available).
    tool_spec = _resolve_tool(tool, url)
    print(f"  Resolved: package={tool_spec.get('package')!r}, readme_chars={len(tool_spec.get('readme', ''))}")

    # 2. Classify.
    if client is None:
        print("  Skipping LLM classification (DRY_RUN without ANTHROPIC_API_KEY)")
        classification = {"category": "unknown", "package": tool_spec.get("package") or tool, "hint": "dry-run skip"}
        cost1 = 0.0
    else:
        classification, cost1 = _classify(client, tool_spec)
    print(f"  Classified as: category={classification.get('category')!r}")

    # 3. Generate test script.
    if client is None:
        test_script = "# Dry-run without ANTHROPIC_API_KEY — script not generated.\n"
        cost2 = 0.0
    else:
        test_script, cost2 = _generate_test(client, tool_spec, classification)

    # 4. Safety scan.
    leak = SECRET_LEAK_RE.search(test_script)
    if leak:
        msg = (
            f":warning: *Lab aborted for {tool}* — the generated test script "
            f"contained what looks like a real secret prefix (`{leak.group(0)[:24]}…`). "
            "Refusing to execute. This is a safety guard against prompt-injection."
        )
        print(msg)
        _post_thread_if_possible(tool, msg, dry_run=dry_run)
        _write_transcript(tool, url, user, classification, test_script, None, {"aborted_reason": "secret_leak_regex"})
        return 0

    # 5. Run the script in a hermetic subprocess (unless dry-run).
    if dry_run:
        print("─── DRY-RUN: generated test script ───")
        print(test_script)
        print("─── END SCRIPT ───")
        return 0

    sandbox_result = _run_subprocess(tool_spec, test_script)
    print(f"  Subprocess: exit={sandbox_result['exit_code']} duration={sandbox_result['duration_s']:.1f}s")

    # 6. Interpret.
    insights, cost3 = _interpret(client, tool_spec, classification, test_script, sandbox_result)

    total_cost = cost1 + cost2 + cost3
    print(f"  Lab cost: ${total_cost:.4f}")

    # 7. Post + commit artifact.
    reply = _format_reply(tool, url, classification, sandbox_result, insights, total_cost)
    _post_thread_if_possible(tool, reply, dry_run=False)
    _write_transcript(tool, url, user, classification, test_script, sandbox_result, insights)
    return 0


# ── Step 0b: cost & frequency caps ───────────────────────────────────────────

def _within_caps() -> str | None:
    """Return None if a new lab run is allowed; else a polite-refusal message.

    Reads today's `lab-*` entries from costs.jsonl (the same ledger every other
    Sonnet call writes to) and applies both the per-day count cap and the
    per-day USD cap.
    """
    today_count, today_usd = _today_lab_usage()
    if today_count >= LAB_RUNS_PER_DAY:
        return (
            f":mute: *Lab paused for today* — daily cap of {LAB_RUNS_PER_DAY} "
            f"reached ({today_count} run{'s' if today_count != 1 else ''} so far). "
            "Resets at midnight UTC."
        )
    if today_usd >= LAB_DAILY_USD_CAP:
        return (
            f":mute: *Lab paused for today* — daily USD cap of "
            f"${LAB_DAILY_USD_CAP:.2f} reached (today's lab spend: ${today_usd:.4f}). "
            "Resets at midnight UTC."
        )
    return None


def _today_lab_usage() -> tuple[int, float]:
    """Count today's lab runs and total USD across all `lab-*` cost entries."""
    if not COSTS_LEDGER.exists():
        return 0, 0.0
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    runs = set()
    total_usd = 0.0
    with COSTS_LEDGER.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not rec.get("ts", "").startswith(today_prefix):
                continue
            comp = rec.get("component", "")
            if not comp.startswith("lab-"):
                continue
            total_usd += float(rec.get("cost_usd", 0) or 0)
            # Count one "run" per unique run_id. Each lab run does 3 calls
            # (classify/generate/interpret) but shares one run_id.
            rid = rec.get("run_id")
            if rid:
                runs.add(rid)
    return len(runs), total_usd


# ── Step 1: resolve tool metadata ────────────────────────────────────────────

def _resolve_tool(tool: str, url: str) -> dict:
    """Fetch README + (when reachable) PyPI metadata. Best-effort: missing
    pieces just leave the dict thin; the generator prompt handles thin specs."""
    spec: dict = {"name": tool, "url": url, "readme": "", "package": None, "pypi": {}}

    # GitHub README via raw URL — try main/master/HEAD.
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#]+)", url)
    if m:
        owner, repo = m.group(1), m.group(2).rstrip(".git")
        for branch in ("main", "master", "HEAD"):
            readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
            text = _http_get(readme_url, timeout=6)
            if text:
                spec["readme"] = text[:6000]  # cap context
                break

    # PyPI metadata (cheap, useful when the tool is a Python package).
    pkg = _guess_pypi_name(tool, url)
    if pkg:
        meta = _http_get_json(f"https://pypi.org/pypi/{pkg}/json", timeout=6)
        if meta:
            info = meta.get("info", {}) or {}
            spec["package"] = pkg
            spec["pypi"] = {
                "summary":     (info.get("summary") or "")[:300],
                "description": (info.get("description") or "")[:2000],
                "version":     info.get("version"),
                "requires_python": info.get("requires_python"),
                "license":     info.get("license"),
                "home_page":   info.get("home_page"),
            }

    return spec


def _guess_pypi_name(tool: str, url: str) -> str | None:
    # If URL is pypi.org/project/X — straight read.
    m = re.match(r"https?://pypi\.org/project/([^/?#]+)", url)
    if m:
        return m.group(1).lower()
    # Otherwise, normalise the tool name and hope.
    candidate = re.sub(r"[^a-zA-Z0-9._-]+", "-", tool.strip()).strip("-").lower()
    return candidate or None


def _http_get(url: str, timeout: int = 6) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "frontier-scout-lab/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return ""
    except Exception as e:  # noqa: BLE001
        print(f"  http_get({url}): {e}")
        return ""


def _http_get_json(url: str, timeout: int = 6) -> dict | None:
    text = _http_get(url, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── Step 2: classify ─────────────────────────────────────────────────────────

_CLASSIFY_TOOL = {
    "name": "classify_tool",
    "description": "Classify the tool into one of the known categories and emit minimal install metadata.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "vector_db", "llm_framework", "evals", "agent_lib",
                    "orchestration", "data_util", "observability", "util",
                ],
            },
            "package": {"type": "string", "description": "PyPI install name. Use the verified pypi.summary if present; otherwise best guess."},
            "hint": {"type": "string", "description": "One-sentence note for the generator — what team usage would look most like this tool."},
        },
        "required": ["category", "package"],
    },
}


def _classify(client: anthropic.Anthropic, spec: dict) -> tuple[dict, float]:
    user_msg = (
        f"Tool name: {spec['name']}\n"
        f"URL: {spec['url']}\n"
        f"PyPI summary: {spec.get('pypi', {}).get('summary', '') or 'n/a'}\n\n"
        f"README excerpt (first 3000 chars):\n{spec.get('readme', '')[:3000]}"
    )
    resp = call_with_retry(
        client, "lab-classify",
        model=MODEL,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": (
            "You are Frontier Scout's lab classifier. Given a tool, decide its "
            "category and emit minimal install metadata via the classify_tool "
            "tool. Be conservative — when in doubt, prefer 'util'."
        )}],
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_tool"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-classify", MODEL, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return dict(tool_use.input), cost


# ── Step 3: generate test script ─────────────────────────────────────────────

_GENERATE_TEST_TOOL = {
    "name": "emit_test_script",
    "description": "Emit a Python 3.11 test script that exercises the tool with synthetic stack-shaped inputs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Complete, runnable Python 3.11 script. Imports + main code in one file.",
            },
            "explanation": {
                "type": "string",
                "description": "1–2 sentences explaining what the script exercises and why this shape is stack-relevant.",
            },
        },
        "required": ["script", "explanation"],
    },
}

_GENERATOR_SYSTEM = (
    "You are Frontier Scout's lab test-script generator. You will receive a tool "
    "name + classification + README + PyPI metadata. Emit a SHORT Python 3.11 "
    "test script that exercises the tool using SYNTHETIC inputs shaped like "
    "the configured stack usage.\n"
    "\n"
    "STRICT RULES:\n"
    "  1. The script runs with env={} + PATH + HOME ONLY. There is NO\n"
    "     ANTHROPIC_API_KEY, OPENAI_API_KEY, SLACK_BOT_TOKEN, GH_TOKEN, or any\n"
    "     other credential in the environment. Do NOT write code that calls any\n"
    "     paid API requiring auth — it will fail. Focus on LOCAL behaviour:\n"
    "     imports, class instantiation, type checks, offline functionality,\n"
    "     in-memory operations, package metadata.\n"
    "  2. NEVER embed real secrets, real internal prompts, or real production\n"
    "     data values. Use clearly synthetic inputs like 'hello world',\n"
    "     placeholder strings, or trivially constructed data structures.\n"
    "  3. Be DEFENSIVE: wrap risky operations in try/except, print clearly\n"
    "     labelled milestones ('importing ...', 'instantiating ...', 'OK:', "
    "'FAILED:'), and exit gracefully on missing optional features. NEVER let\n"
    "     an uncaught exception abort the script silently — exit code 0 is\n"
    "     for 'meaningful run completed', not 'never tried'.\n"
    "  4. Be SHORT — aim for 30–80 lines. Print at most ~50 lines of stdout.\n"
    "  5. Python 3.11 syntax. Stdlib + the tool only (no extra pip installs).\n"
    "  6. If the tool genuinely needs an LLM API key to do anything meaningful,\n"
    "     the right test is to verify import + class introspection + show what\n"
    "     'this would do if it had a key'. Don't try to fake a key.\n"
    "\n"
    "TARGET STACK (so the synthetic inputs feel relevant):\n"
    f"{STACK}\n"
)


def _generate_test(client: anthropic.Anthropic, spec: dict, classification: dict) -> tuple[str, float]:
    user_msg = (
        f"Tool: {spec['name']}\n"
        f"Category: {classification.get('category')}\n"
        f"Package: {classification.get('package')}\n"
        f"Hint: {classification.get('hint', '')}\n"
        f"URL: {spec['url']}\n\n"
        f"PyPI summary: {spec.get('pypi', {}).get('summary', '') or 'n/a'}\n"
        f"PyPI version: {spec.get('pypi', {}).get('version', '') or 'n/a'}\n\n"
        f"README excerpt (first 4000 chars):\n{spec.get('readme', '')[:4000]}\n\n"
        "Emit a single test script via emit_test_script."
    )
    resp = call_with_retry(
        client, "lab-generate",
        model=MODEL,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": _GENERATOR_SYSTEM}],
        tools=[_GENERATE_TEST_TOOL],
        tool_choice={"type": "tool", "name": "emit_test_script"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-generate", MODEL, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    script = tool_use.input["script"]
    return script, cost


# ── Step 5: run subprocess in hermetic env ───────────────────────────────────

def _run_subprocess(spec: dict, script: str) -> dict:
    """pip install the tool into a venv-less tempdir target, then run the
    generated test with a minimal env. Returns a dict the interpreter can
    reason about."""
    package = spec.get("package") or spec["name"]
    start = datetime.now()
    with tempfile.TemporaryDirectory(prefix="ai-lab-") as td:
        tdp = Path(td)
        # Install target dir for the tool's site-packages
        target = tdp / "pkg"
        target.mkdir()
        script_path = tdp / "lab_test.py"
        script_path.write_text(script)

        # Install. Use --target so we don't touch the host site-packages.
        install_cmd = [
            sys.executable, "-m", "pip", "install",
            "--quiet",
            "--target", str(target),
            "--disable-pip-version-check",
            "--no-input",
            package,
        ]
        try:
            install_proc = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return _result(start, -1, "", f"pip install timed out after {SUBPROCESS_TIMEOUT}s")

        if install_proc.returncode != 0:
            return _result(
                start, install_proc.returncode,
                install_proc.stdout[-2000:],
                f"pip install failed:\n{install_proc.stderr[-2000:]}",
                stage="install",
            )

        # Run the script with HERMETIC env. The child has NO API keys,
        # NO Slack token, NO BB token — it physically cannot call any
        # paid API, so it can't burn quota and can't exfil secrets.
        run_env = {
            "PATH":           os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME":           os.environ.get("HOME", "/tmp"),
            "PYTHONPATH":     str(target),
            "PYTHONIOENCODING": "utf-8",
            "LANG":           "C.UTF-8",
            "LC_ALL":         "C.UTF-8",
        }
        try:
            run_proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                env=run_env,
                cwd=str(tdp),
            )
        except subprocess.TimeoutExpired:
            return _result(
                start, -1, "", f"test script timed out after {SUBPROCESS_TIMEOUT}s wall clock",
                stage="run",
            )

        return _result(
            start,
            run_proc.returncode,
            run_proc.stdout[-4000:],
            run_proc.stderr[-4000:],
            stage="run",
        )


def _result(start: datetime, exit_code: int, stdout: str, stderr: str, stage: str = "install") -> dict:
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_s": (datetime.now() - start).total_seconds(),
        "stage": stage,
    }


# ── Step 6: interpret ────────────────────────────────────────────────────────

_INTERPRET_TOOL = {
    "name": "emit_lab_insights",
    "description": "Interpret the lab run and emit structured insights for the Slack thread reply.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One sentence: would this be useful for the team?"},
            "verdict_for_team": {"type": "string", "enum": ["worth_trial", "monitor", "skip"]},
            "what_worked": {"type": "string", "description": "1–2 sentences on what the script confirmed."},
            "what_didnt": {"type": "string", "description": "1–2 sentences on what failed or was unclear (or 'nothing — clean run')."},
            "next_step": {"type": "string", "description": "Concrete recommendation, e.g. 'lab <tool>' or 'add to tech-radar at TRIAL' or 'no further action'."},
            "test_quality_self_rating": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["headline", "verdict_for_team", "what_worked", "what_didnt", "next_step", "test_quality_self_rating"],
    },
}


def _interpret(client: anthropic.Anthropic, spec: dict, classification: dict, script: str, sandbox: dict) -> tuple[dict, float]:
    user_msg = (
        f"Tool: {spec['name']}\nCategory: {classification.get('category')}\n"
        f"Subprocess exit_code: {sandbox['exit_code']} (stage: {sandbox['stage']})\n"
        f"Duration: {sandbox['duration_s']:.1f}s\n\n"
        f"--- generated test script ---\n{script}\n\n"
        f"--- stdout (last 4000 chars) ---\n{sandbox['stdout']}\n\n"
        f"--- stderr (last 4000 chars) ---\n{sandbox['stderr']}\n\n"
        "Emit insights via emit_lab_insights. Be honest about whether the "
        "script actually exercised anything meaningful — if it just confirmed "
        "imports, say so and rate test_quality_self_rating='low'."
    )
    resp = call_with_retry(
        client, "lab-interpret",
        model=MODEL,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": (
            "You are Frontier Scout's lab interpreter. Given a sandbox run, "
            "emit structured insights for the team. Be terse, stack-specific, "
            "and HONEST about confidence. Anchor the recommendation to the "
            "Configured stack:\n" + STACK
        )}],
        tools=[_INTERPRET_TOOL],
        tool_choice={"type": "tool", "name": "emit_lab_insights"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-interpret", MODEL, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return dict(tool_use.input), cost


# ── Step 7: format reply + post to Slack + write transcript ──────────────────

_VERDICT_LABEL = {
    "worth_trial": "🟡 worth a TRIAL",
    "monitor":     "⚪ MONITOR for now",
    "skip":        "🔴 SKIP",
}
_QUALITY_LABEL = {
    "high":   ":white_check_mark: high-confidence test",
    "medium": ":large_blue_circle: medium-confidence test",
    "low":    ":warning: best-effort test (imports/smoke only)",
}


def _format_reply(tool: str, url: str, classification: dict, sandbox: dict, insights: dict, cost: float) -> str:
    pkg = classification.get("package") or tool
    stage_label = "pip install" if sandbox["stage"] == "install" else "script run"
    exit_line = (
        f":white_check_mark: clean run (exit 0)" if sandbox["exit_code"] == 0
        else f":x: {stage_label} failed (exit {sandbox['exit_code']})"
    )
    return (
        f":test_tube: *Lab results — `{tool}`*\n"
        f"_Category: {classification.get('category')} · Package: `{pkg}` · "
        f"Duration: {sandbox['duration_s']:.1f}s · Cost: ${cost:.3f}_\n"
        f"\n"
        f"*Headline*: {insights['headline']}\n"
        f"*Verdict for team*: {_VERDICT_LABEL.get(insights['verdict_for_team'], insights['verdict_for_team'])}\n"
        f"*What worked*: {insights['what_worked']}\n"
        f"*What didn't*: {insights['what_didnt']}\n"
        f"*Next step*: {insights['next_step']}\n"
        f"\n"
        f"{exit_line}  ·  {_QUALITY_LABEL.get(insights['test_quality_self_rating'], '')}\n"
        f"\n"
        f"_Hermetic subprocess (no API keys in child env). Full transcript committed under `.scratch/labs/`._"
    )


def _post_thread_if_possible(tool: str, text: str, dry_run: bool) -> None:
    """Post `text` as a threaded reply on the verdict card for `tool`.

    Resolves the message_ts by walking briefings/*-meta.json newest first
    (same map Round 6's reaction dispatcher uses). Falls back to channel
    post if no match is found — better to ship the insight than swallow it.
    """
    if dry_run:
        print("─── DRY-RUN: would post to Slack ───")
        print(text)
        print("─── END ───")
        return

    thread_ts = _find_thread_ts(tool)
    try:
        from slack_post import _post_thread_reply, post
    except Exception as e:  # noqa: BLE001
        print(f"  slack_post import failed: {e}")
        return

    try:
        if thread_ts:
            _post_thread_reply(thread_ts, blocks=None, attachments=None, text_fallback=text)
            # The above sends with no blocks — Slack treats `text` as the
            # message body. Provide the text via the existing kwarg path.
            # (Defensive: if blocks=None is rejected, fall back to channel.)
        else:
            print(f"  No verdict thread found for {tool!r} — posting to channel")
            post([{"type": "section", "text": {"type": "mrkdwn", "text": text}}])
    except Exception as e:  # noqa: BLE001
        print(f"  Slack post failed: {e}")


def _find_thread_ts(tool: str) -> str | None:
    """Find the most recent verdict card message_ts whose tool matches."""
    if not BRIEFINGS_DIR.exists():
        return None
    tool_lc = tool.strip().lower()
    if not tool_lc:
        return None
    for path in sorted(BRIEFINGS_DIR.glob("*-meta.json"), reverse=True)[:8]:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for ts, meta in (data.get("verdicts") or {}).items():
            if (meta.get("tool") or "").strip().lower() == tool_lc:
                return ts
    return None


def _write_transcript(
    tool: str, url: str, user: str,
    classification: dict, script: str,
    sandbox: dict | None, insights: dict | None,
) -> Path:
    LABS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", tool.lower()).strip("-") or "unknown"
    path = LABS_DIR / f"{today}-{slug}.md"
    body = (
        f"# Lab transcript: {tool}\n\n"
        f"_Ran by @{user or 'anon'} on {today} via 🧪 click in Slack._\n\n"
        f"Source: {url}\n\n"
        f"## Classification\n```json\n{json.dumps(classification, indent=2)}\n```\n\n"
        f"## Generated test script\n```python\n{script}\n```\n\n"
        f"## Sandbox result\n```json\n{json.dumps(sandbox or {}, indent=2)}\n```\n\n"
        f"## Insights\n```json\n{json.dumps(insights or {}, indent=2)}\n```\n"
    )
    path.write_text(body)
    print(f"  Transcript → {path}")
    return path


# ── Misc helpers ─────────────────────────────────────────────────────────────

def _anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


if __name__ == "__main__":
    sys.exit(main())
