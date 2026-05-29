#!/usr/bin/env python3
"""
Frontier Scout — local polyglot lab runner.

What the lab does (`frontier-scout lab`, ~5-10 min):

  1. Classify the tool (1 Sonnet call) — {vector_db, llm_framework, …}
  2. Generate a stack-shaped synthetic test script (1 Sonnet call)
     using the existing `cached_system_blocks` knowledge of the configured stack
     (FastAPI + LangGraph + Anthropic + Python 3.11)
  3. Safety-scan the script for secret-leak patterns; abort if found
  4. Subprocess `pip install <tool>` then run the test with env={} +
     PATH + HOME ONLY. The child process literally cannot call any paid
     API because it has no key. 3-min wall-clock timeout.
  5. Interpret the captured stdout/stderr/exit_code (1 Sonnet call)
  6. Write a full local transcript to .scratch/labs/<date>-<tool>.md

Cost guardrails (all in this file, all overridable via env):

  LAB_RUNS_PER_DAY=1          — caps lab clicks per UTC day
  LAB_DAILY_USD_CAP=1.00      — reads costs.jsonl, refuses if today >= cap
  LAB_SUBPROCESS_TIMEOUT=180  — 3-minute wall clock on the child process
  LAB_MAX_TOKENS=2000         — per Sonnet call

If either cap fires the lab posts a polite refusal instead of running.

Trust boundary:

  • subprocess.run(env={...minimal...}) — no app secret reaches the
    generated script.
  • Synthetic-only generator prompt + a SECRET_LEAK_RE pre-check before
    execution.
  • Output is read-only: .scratch/labs/ artifact plus terminal output.
    The lab never modifies any application repo, posts remotely, or pushes a PR.

Usage:

  python scripts/lab_runner.py --tool dspy \\
      --url https://github.com/stanfordnlp/dspy

  # Dry-run (no subprocess, no API calls when ANTHROPIC_API_KEY is absent):
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


from cost_tracker import log_call
from llm_client import call_with_retry

from frontier_scout.providers import FAST, available_providers, resolve_provider


def _fs_home() -> Path:
    """Resolve Frontier Scout's local home directory.

    ``$FRONTIER_SCOUT_HOME`` overrides; otherwise we fall back to the repo
    root so direct ``python scripts/lab_runner.py`` runs still work in dev.
    """
    home_env = os.environ.get("FRONTIER_SCOUT_HOME")
    if home_env:
        return Path(home_env).expanduser()
    return Path(__file__).resolve().parent.parent


REPO_ROOT = _fs_home()
LABS_DIR = REPO_ROOT / ".scratch" / "labs"
COSTS_LEDGER = REPO_ROOT / "costs.jsonl"


# Light-weight "what to write the synthetic test for" note shared by all three
# runtime generator prompts. The lab is a generic black-box test (does this
# package import? does its main class instantiate?) so the user's exact stack
# doesn't change how the script gets written — only the interpreter's later
# "does this fit your stack?" reasoning needs the profile, and that lives in
# the scout / MCP layer.
_LAB_CONTEXT_NOTE = (
    "TARGET CONTEXT: synthetic-only test for a polyglot lab dispatcher. The\n"
    "user runs Claude Code / Cursor on a personal laptop; inputs should look\n"
    "like the kind of toy data a solo developer would type to smoke-test a\n"
    "new tool ('hello world', a 3-line JSON snippet, a 2-row CSV)."
)

MODEL = "claude-sonnet-4-6"

# ── Cost & safety guardrails ─────────────────────────────────────────────────
#
# Defaults are sized for normal local usage, not "demo at all costs."
# Override via env vars when a particular lab run needs more room.
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

# Round 10: HuggingFace model size cap. The HF dispatcher reads the model
# repo's file manifest before downloading anything; if total weight files
# exceed this, the lab skips with a clear message. Sized to leave headroom
# in a normal hosted runner or developer workstation while covering most HF
# models Scout surfaces (everything except the largest frontier checkpoints).
_HF_MODEL_SIZE_CAP_GB = float(os.environ.get("LAB_HF_SIZE_CAP_GB", "5"))

# Runtimes the polyglot dispatcher knows how to exercise (Round 10).
# Cargo + Docker defer to Round 11 — each needs its own toolchain in the
# pipeline image + its own generator prompt.
_SUPPORTED_RUNTIMES = ("python", "node", "huggingface")

# Only labs on real open-source URLs. Closed-source tools shouldn't even
# have the button surfaced; this is the second line of defence.
OPEN_SOURCE_URL_RE = re.compile(
    r"^https?://(www\.)?(github\.com|pypi\.org|huggingface\.co|gitlab\.com)/",
    re.IGNORECASE,
)


def is_open_source_url(url: str | None) -> bool:
    """True if ``url`` is one of the four public-repo hosts the lab can pull
    from (github.com / pypi.org / huggingface.co / gitlab.com). Surfaces are
    expected to call this *before* offering a "Try it" button — exposing the
    button on a vendor-blog URL just queues a guaranteed-to-fail run.
    """
    return bool(url) and OPEN_SOURCE_URL_RE.match(url) is not None

# If Sonnet ever emits one of these in the generated test script, refuse to
# execute. Belt-and-braces against prompt injection that tries to bake real
# secrets into the script. Patterns cover every credential shape the lab
# could plausibly receive across Python / Node / HF runtimes.
SECRET_LEAK_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{20,}"
    r"|sk-proj-[A-Za-z0-9_-]{20,}"
    r"|xoxb-[A-Za-z0-9_-]{20,}"
    r"|xoxa-[A-Za-z0-9_-]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|npm_[A-Za-z0-9]{36,}"            # Round 10: npm personal access tokens
    r"|ASIA[A-Z0-9]{12,}"
    r"|AKIA[A-Z0-9]{12,})",
)

# Hermetic env keys that are SAFE to pass through to the child. Everything
# else from os.environ is dropped — in particular the credentials. This is
# the central anti-exfiltration guarantee; see `tests/test_pipeline_bits.py
# ::TestLabRuntimeDispatch::test_subprocess_env_has_no_secrets` for the
# regression test.
_HERMETIC_ENV_PASSTHROUGH = ("PATH", "HOME")


# ── Public entry points ──────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Frontier Scout lab runner")
    parser.add_argument("--tool", required=True, help="Tool name as it appears on the verdict card")
    parser.add_argument("--url", required=True, help="Open-source source URL")
    parser.add_argument("--user", default="", help="Optional label for the transcript")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip subprocess execution; print classification/script preview only",
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

    client = _provider() if (not dry_run or available_providers()) else None

    # 1. Resolve tool (deterministic — README + PyPI/HF metadata when reachable).
    tool_spec = _resolve_tool(tool, url)
    print(f"  Resolved: package={tool_spec.get('package')!r}, readme_chars={len(tool_spec.get('readme', ''))}")

    # 2. Classify — this picks both the category AND the runtime
    #    (python / node / huggingface / unknown).
    if client is None:
        print("  Skipping LLM classification (DRY_RUN without ANTHROPIC_API_KEY)")
        # Best-effort runtime guess for dry-run: huggingface URL → HF, else python.
        dry_runtime = "huggingface" if "huggingface.co" in url.lower() else "python"
        classification = {
            "category": "unknown",
            "runtime": dry_runtime,
            "package": tool_spec.get("package") or tool,
            "hint": "dry-run skip",
        }
        cost1 = 0.0
    else:
        classification, cost1 = _classify(client, tool_spec)
    print(f"  Classified as: category={classification.get('category')!r} runtime={classification.get('runtime')!r}")

    # 2b. Pre-flight: can we actually exercise this with the picked runtime?
    # Round 10 polyglot gate — replaces Round 9's pip-only check. Handles:
    #   • unsupported runtimes (cargo, docker, unknown)
    #   • non-library README signals (skill collections, prompt sets)
    #   • HF gated/private/over-cap models
    # The skip path posts an honest "lab can't exercise this" reply rather
    # than wasting two more Sonnet calls + a doomed install on a no-op.
    skip_reason = _unsupported_runtime_reason(tool_spec, classification, url)
    if skip_reason is not None:
        msg = (
            f":information_source: *Lab skipped for {tool}* — {skip_reason} "
            "The lab today exercises Python (pip), Node (npm), and HuggingFace "
            "models (config + tokenizer only). For non-library assets (skill "
            "collections, prompt sets, design docs), try `/recall <topic>` or "
            "read the repo directly."
        )
        print(msg)
        _post_thread_if_possible(tool, msg, dry_run=dry_run)
        _write_transcript(tool, url, user, classification, "", None,
                          {"skipped_reason": "unsupported_runtime",
                           "skip_detail": skip_reason})
        return 0

    # 3. Generate test script (per-runtime system prompt).
    if client is None:
        test_script = "// Dry-run without ANTHROPIC_API_KEY — script not generated.\n"
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
        print(f"─── DRY-RUN: generated {classification.get('runtime')} test script ───")
        print(test_script)
        print("─── END SCRIPT ───")
        return 0

    sandbox_result = _dispatch_subprocess(tool_spec, classification, test_script)
    print(f"  Subprocess: runtime={classification.get('runtime')!r} exit={sandbox_result['exit_code']} duration={sandbox_result['duration_s']:.1f}s")

    # 6. Interpret.
    insights, cost3 = _interpret(client, tool_spec, classification, test_script, sandbox_result)

    total_cost = cost1 + cost2 + cost3
    print(f"  Lab cost: ${total_cost:.4f}")

    # 7. Print summary + write local artifact.
    excerpt = _test_excerpt(test_script)
    _post_lab_reply(
        tool=tool, url=url,
        classification=classification, sandbox=sandbox_result,
        insights=insights, cost=total_cost,
        test_excerpt=excerpt,
        dry_run=False,
    )
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
    """Fetch README + (when reachable) PyPI / HF metadata. Best-effort:
    missing pieces just leave the dict thin; the generator prompt handles
    thin specs."""
    spec: dict = {
        "name": tool, "url": url, "readme": "",
        "package": None, "pypi": {}, "hf": {},
    }

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

    # Round 10: HuggingFace manifest (cheap one-HTTP-GET, lets us size-cap
    # the lab BEFORE downloading any weights).
    hf_slug = _hf_slug_from_url(url)
    if hf_slug:
        spec["hf"] = _hf_manifest(hf_slug)
        # If we have HF metadata, the package identifier becomes the slug.
        if spec["hf"]:
            spec["package"] = hf_slug

    return spec


def _hf_slug_from_url(url: str) -> str | None:
    """Extract `<owner>/<repo>` from a HuggingFace model URL. Returns None
    for non-HF URLs or unparseable shapes."""
    m = re.match(
        r"https?://(?:www\.)?huggingface\.co/([^/?#]+)/([^/?#]+)",
        url, re.IGNORECASE,
    )
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


# Weight-file extensions HuggingFace uses. Sums of these are what we cap
# against — config.json / tokenizer.json are tiny and always allowed.
_HF_WEIGHT_EXTENSIONS = (".safetensors", ".bin", ".pt", ".pth", ".gguf", ".onnx", ".msgpack")


def _hf_manifest(slug: str) -> dict:
    """Fetch HF model metadata + compute total weight-file bytes.

    Returns a dict shaped like::

        {
            "model_type":         "qwen2",
            "library_name":       "transformers",
            "gated":              False,
            "private":            False,
            "total_weight_bytes": 7_834_829_312,
            "weight_file_count":  4,
        }

    Returns ``{}`` on any error so the caller's gate can still decide.
    """
    meta = _http_get_json(f"https://huggingface.co/api/models/{slug}", timeout=8)
    if not meta:
        return {}
    siblings = meta.get("siblings") or []
    total = 0
    n_weights = 0
    for s in siblings:
        name = (s.get("rfilename") or "").lower()
        size = int(s.get("size") or 0)
        if any(name.endswith(ext) for ext in _HF_WEIGHT_EXTENSIONS):
            total += size
            n_weights += 1
    return {
        "model_type":         (meta.get("config") or {}).get("model_type", ""),
        "library_name":       meta.get("library_name", ""),
        "gated":               bool(meta.get("gated", False)),
        "private":             bool(meta.get("private", False)),
        "total_weight_bytes":  total,
        "weight_file_count":   n_weights,
    }


def _hf_total_weight_bytes(spec: dict) -> int:
    """Convenience accessor — returns 0 when the manifest is missing."""
    hf = spec.get("hf") or {}
    return int(hf.get("total_weight_bytes") or 0)


def _guess_pypi_name(tool: str, url: str) -> str | None:
    # If URL is pypi.org/project/X — straight read.
    m = re.match(r"https?://pypi\.org/project/([^/?#]+)", url)
    if m:
        return m.group(1).lower()
    # Otherwise, normalise the tool name and hope.
    candidate = re.sub(r"[^a-zA-Z0-9._-]+", "-", tool.strip()).strip("-").lower()
    return candidate or None


# README signals that strongly suggest a repo is NOT a runnable library, even
# if classification names a runtime. Skills repos / prompt sets / design docs.
_NON_LIBRARY_README_HINTS = (
    "skills are markdown",
    "this repository contains skills",
    "this repo contains prompt",
    "collection of prompts",
    "collection of skills",
    "no python package",
    "not a python library",
    "not a package",
)


def _unsupported_runtime_reason(spec: dict, classification: dict, url: str) -> str | None:
    """Return a one-line reason if the lab can't exercise this tool, else None.

    Replaces Round 9's pip-only `_not_pip_installable_reason`. Round 10
    supports python / node / huggingface; anything else (cargo, docker,
    "this is just a skill collection") returns a skip reason so the caller
    posts an honest "lab can't exercise this" reply rather than wasting
    LLM tokens on a doomed install.
    """
    runtime = classification.get("runtime", "unknown")

    if runtime not in _SUPPORTED_RUNTIMES:
        return (
            f"the lab classifier picked runtime={runtime!r}, which isn't "
            f"in the supported set {_SUPPORTED_RUNTIMES}. (Cargo and Docker "
            f"land in Round 11.)"
        )

    # Even when a runtime is picked, the README sometimes makes it obvious
    # this isn't a runnable library at all (skill collections / prompt sets).
    readme_lower = (spec.get("readme") or "").lower()
    for hint in _NON_LIBRARY_README_HINTS:
        if hint in readme_lower:
            return f"the README indicates this isn't a runnable library ('{hint}')."

    # Per-runtime sanity checks.
    if runtime == "python":
        pypi = spec.get("pypi") or {}
        if not pypi.get("version") and not classification.get("package"):
            return "no matching PyPI package found for this repo."

    if runtime == "huggingface":
        hf = spec.get("hf") or {}
        if not hf:
            return "this URL is on huggingface.co but the HF API returned no manifest."
        if hf.get("gated"):
            return "this HuggingFace model is gated — the lab runs unauthenticated and can't access it."
        if hf.get("private"):
            return "this HuggingFace model is private — the lab can't access it."
        weight_bytes = int(hf.get("total_weight_bytes") or 0)
        cap_bytes = int(_HF_MODEL_SIZE_CAP_GB * 1024 ** 3)
        if weight_bytes > cap_bytes:
            gb = weight_bytes / (1024 ** 3)
            return (
                f"model weights total {gb:.1f} GB, over the lab's "
                f"{_HF_MODEL_SIZE_CAP_GB:.0f} GB cap. Set `LAB_HF_SIZE_CAP_GB` "
                f"higher if you really want to override, but expect long pipeline times."
            )

    # Node sanity is minimal — npm registry lookups would add latency
    # without much value over letting `npm install` fail cleanly. The
    # generator prompt + interpreter pair handle missing-package failures
    # with a clear MONITOR ("npm install: 404 Not Found") verdict.

    return None


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
    "description": "Classify the tool into one of the known categories and emit minimal install metadata, including which runtime can exercise it.",
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
            "runtime": {
                "type": "string",
                "description": (
                    "Which runtime the lab should use. 'python' = pip-installable "
                    "Python library. 'node' = npm-installable Node CLI or library "
                    "(README mentions `npm install` / `npx` or repo has package.json). "
                    "'huggingface' = HF model repo at huggingface.co (verify config + "
                    "tokenizer loads, no inference). 'unknown' = none of the above — "
                    "the dispatcher will skip with an honest message."
                ),
                "enum": ["python", "node", "huggingface", "unknown"],
            },
            "package": {
                "type": "string",
                "description": (
                    "Install identifier for the chosen runtime. For runtime=python: "
                    "the PyPI install name. For runtime=node: the npm package name "
                    "(prefer the registry name; fall back to the github tarball URL "
                    "only if no published package). For runtime=huggingface: the "
                    "<owner>/<repo> slug exactly as it appears in the URL. For "
                    "runtime=unknown: empty string."
                ),
            },
            "hint": {"type": "string", "description": "One-sentence note for the generator — what team usage would look most like this tool."},
        },
        "required": ["category", "runtime", "package"],
    },
}


def _classify(client, spec: dict) -> tuple[dict, float]:
    model_id = client.model(FAST)
    user_msg = (
        f"Tool name: {spec['name']}\n"
        f"URL: {spec['url']}\n"
        f"PyPI summary: {spec.get('pypi', {}).get('summary', '') or 'n/a'}\n"
        f"HF manifest weight bytes: {spec.get('hf', {}).get('total_weight_bytes', 'n/a')}\n\n"
        f"README excerpt (first 3000 chars):\n{spec.get('readme', '')[:3000]}"
    )
    resp = call_with_retry(
        client, "lab-classify",
        model=model_id,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": (
            "You are Frontier Scout's lab classifier. Given a tool, decide its "
            "category AND which runtime can exercise it (python / node / "
            "huggingface / unknown), and emit minimal install metadata via the "
            "classify_tool tool.\n"
            "\n"
            "Runtime selection cues:\n"
            "  - URL host huggingface.co → runtime='huggingface' (model repo)\n"
            "  - PyPI summary present, or README has `pip install` → runtime='python'\n"
            "  - README mentions `npm install` / `npx` / package.json, or URL "
            "    points to a known JS tool → runtime='node'\n"
            "  - None of the above → runtime='unknown' (lab will skip honestly)\n"
            "\n"
            "When the README signals both Python and Node (some MCP servers ship "
            "both), prefer Python if a PyPI package exists, else Node.\n"
            "\n"
            "Be conservative — when in doubt about category, prefer 'util'. When "
            "in doubt about runtime, prefer 'unknown' over guessing wrong."
        )}],
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_tool"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-classify", getattr(resp, "model", None) or model_id, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    out = dict(tool_use.input)
    # Backward-safety: if the classifier somehow omits runtime, default to
    # 'unknown' so the unsupported-runtime gate handles it cleanly.
    out.setdefault("runtime", "unknown")
    return out, cost


# ── Step 3: generate test script ─────────────────────────────────────────────

_GENERATE_TEST_TOOL = {
    "name": "emit_test_script",
    "description": "Emit a short test script that exercises the tool with synthetic stack-shaped inputs in the chosen runtime.",
    "input_schema": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Complete, runnable single-file script in the runtime the classifier picked.",
            },
            "explanation": {
                "type": "string",
                "description": "1–2 sentences explaining what the script exercises and why this shape is team-relevant.",
            },
        },
        "required": ["script", "explanation"],
    },
}

_GENERATOR_SYSTEM_PYTHON = (
    "You are Frontier Scout's lab test-script generator (Python runtime). You "
    "will receive a tool name + classification + README + PyPI metadata. Emit "
    "a SHORT Python 3.11 test script that exercises the tool using SYNTHETIC "
    "inputs shaped like the configured stack usage.\n"
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
    f"\n{_LAB_CONTEXT_NOTE}\n"
)

_GENERATOR_SYSTEM_NODE = (
    "You are Frontier Scout's lab test-script generator (Node runtime). You "
    "will receive a tool name + classification + README. Emit a SHORT "
    "single-file Node.js (CommonJS, Node 20+) test script that exercises the "
    "tool using SYNTHETIC inputs.\n"
    "\n"
    "STRICT RULES:\n"
    "  1. The script runs with env={} + PATH + HOME + NODE_PATH ONLY. There "
    "     are NO API keys, NO tokens, NO CI credentials in the\n"
    "     environment. Do NOT write code that calls any paid API requiring\n"
    "     auth — it will fail. Focus on LOCAL behaviour: require + class\n"
    "     instantiation + offline methods + package metadata.\n"
    "  2. NEVER embed real secrets, real prompts, or production data.\n"
    "     Use synthetic inputs like 'hello world' or trivial objects.\n"
    "  3. Be DEFENSIVE: wrap risky `require()` and method calls in try/catch.\n"
    "     Print clearly labelled milestones ('importing ...', 'OK:', 'FAILED:').\n"
    "     NEVER let an uncaught exception abort silently — process exit 0 is\n"
    "     for 'meaningful run completed', not 'never tried'.\n"
    "  4. Be SHORT — aim for 30–80 lines. Print at most ~50 lines of stdout.\n"
    "  5. Node 20+ syntax (CommonJS `require()` is fine). Use only the tool's\n"
    "     package + Node stdlib. Do NOT add extra `npm install`s in the script.\n"
    "  6. If the tool is an ESM-only package (no `main` export, only `exports`),\n"
    "     use dynamic import: `(async () => { const m = await import('pkg'); … })()`.\n"
    "  7. If the tool genuinely needs an LLM API key, the right test is to\n"
    "     verify require + class introspection + show what 'this would do if\n"
    "     it had a key'. Don't fake a key.\n"
    "\n"
    f"\n{_LAB_CONTEXT_NOTE}\n"
    "Note: this is a generic personal-laptop context; JS tests should validate the\n"
    "JS tool's surface, not call into another runtime.\n"
)

_GENERATOR_SYSTEM_HF = (
    "You are Frontier Scout's lab test-script generator (HuggingFace runtime). "
    "You will receive a HF model repo slug + classification + README. Emit a "
    "SHORT Python 3.11 test script that verifies the model can be LOADED — "
    "config + tokenizer + architecture introspection only. NEVER run\n"
    "inference. NEVER download full model weights.\n"
    "\n"
    "STRICT RULES:\n"
    "  1. The script runs with env={} + PATH + HOME + PYTHONPATH ONLY. NO\n"
    "     HF token, NO API keys. The model repo must be PUBLIC; if it's\n"
    "     gated, print a clear 'FAILED: model is gated' and exit cleanly.\n"
    "  2. Use only `huggingface_hub` and `transformers` (both already\n"
    "     installed in the lab's site-packages target). Do NOT import torch,\n"
    "     tensorflow, or jax. Do NOT call `from_pretrained` with\n"
    "     `torch_dtype=` or similar weight-loading arguments.\n"
    "  3. The canonical script shape:\n"
    "       from huggingface_hub import hf_hub_download\n"
    "       from transformers import AutoConfig, AutoTokenizer\n"
    "       cfg = AutoConfig.from_pretrained('OWNER/REPO')\n"
    "       tok = AutoTokenizer.from_pretrained('OWNER/REPO')\n"
    "       print('OK: model_type =', cfg.model_type)\n"
    "       print('OK: hidden_size =', getattr(cfg, 'hidden_size', 'n/a'))\n"
    "       print('OK: vocab_size  =', cfg.vocab_size)\n"
    "       print('OK: tokenizer encoded hello world =', tok.encode('hello world'))\n"
    "  4. Wrap each step in try/except. Print 'FAILED: <step>: <err>' and\n"
    "     exit 0 — interpretation is the judge's job.\n"
    "  5. NEVER call `AutoModel.from_pretrained` — that downloads the\n"
    "     weights. Stay at the config + tokenizer level.\n"
    "  6. Be SHORT — aim for 20–50 lines.\n"
    "\n"
    f"\n{_LAB_CONTEXT_NOTE}\n"
    "Note: model fit (does this checkpoint fit the user's stack?) is judged\n"
    "downstream by the interpreter — your job here is just 'does the model load?'.\n"
)

# Per-runtime generator system prompt dispatch.
_GENERATOR_SYSTEM_BY_RUNTIME = {
    "python":      _GENERATOR_SYSTEM_PYTHON,
    "node":        _GENERATOR_SYSTEM_NODE,
    "huggingface": _GENERATOR_SYSTEM_HF,
}


def _generate_test(client, spec: dict, classification: dict) -> tuple[str, float]:
    model_id = client.model(FAST)
    runtime = classification.get("runtime", "python")
    system_prompt = _GENERATOR_SYSTEM_BY_RUNTIME.get(runtime, _GENERATOR_SYSTEM_PYTHON)
    hf_meta = spec.get("hf", {}) or {}
    user_msg = (
        f"Tool: {spec['name']}\n"
        f"Category: {classification.get('category')}\n"
        f"Runtime: {runtime}\n"
        f"Package: {classification.get('package')}\n"
        f"Hint: {classification.get('hint', '')}\n"
        f"URL: {spec['url']}\n\n"
        f"PyPI summary: {spec.get('pypi', {}).get('summary', '') or 'n/a'}\n"
        f"PyPI version: {spec.get('pypi', {}).get('version', '') or 'n/a'}\n"
        f"HF model_type: {hf_meta.get('model_type', 'n/a')}\n"
        f"HF total weight bytes: {hf_meta.get('total_weight_bytes', 'n/a')}\n\n"
        f"README excerpt (first 4000 chars):\n{spec.get('readme', '')[:4000]}\n\n"
        "Emit a single test script via emit_test_script."
    )
    resp = call_with_retry(
        client, "lab-generate",
        model=model_id,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": system_prompt}],
        tools=[_GENERATE_TEST_TOOL],
        tool_choice={"type": "tool", "name": "emit_test_script"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-generate", getattr(resp, "model", None) or model_id, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    script = tool_use.input["script"]
    return script, cost


# ── Step 5: dispatch + per-runtime subprocess runners ────────────────────────


def _hermetic_base_env(*, temp_home: Path | None = None) -> dict:
    """Return the minimal pass-through env every runtime starts from.

    Pulls ONLY ``PATH`` from os.environ. By construction this never
    contains ANTHROPIC_API_KEY, GH_TOKEN, SLACK_BOT_TOKEN, OPENAI_API_KEY,
    AWS_ACCESS_KEY_ID, or any other credential the parent has in env.

    ``HOME`` is set to ``temp_home`` when provided; callers in lab paths
    pass a fresh temp dir so untrusted code cannot read SSH keys,
    `~/.aws/credentials`, `~/.npmrc`, `~/.pip/pip.conf`, `~/.huggingface/`,
    or any other parent-home secret. The legacy "real HOME" path is kept
    only as a fallback for callers that haven't migrated yet — the v1.2.1
    Codex review (finding #1) flagged real HOME as a hermeticity hole.
    """

    home_value = str(temp_home) if temp_home is not None else os.environ.get("HOME", "/tmp")
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home_value,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _neutralised_env(temp_dir: Path) -> dict:
    """Hermetic env for install-time subprocesses.

    Builds on ``_hermetic_base_env(temp_home=temp_dir)`` and adds explicit
    neutralisers for pip/npm/HuggingFace configuration sources that would
    otherwise read from the user's real home or workstation. Used by every
    install subprocess (pip, HF, npm). Closes Codex finding #1.
    """

    env = _hermetic_base_env(temp_home=temp_dir)
    # pip: no user/global config, no implicit input prompts, no extra indexes.
    pip_index = os.environ.get("LAB_PIP_INDEX_URL", "")
    env.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_INDEX_URL": pip_index,
            "PIP_EXTRA_INDEX_URL": "",
            "PIP_NO_INPUT": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    # Hugging Face: cache + telemetry under temp; never use parent token.
    env.update(
        {
            "HF_HOME": str(temp_dir / "hf"),
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "TRANSFORMERS_CACHE": str(temp_dir / "hf" / "transformers"),
        }
    )
    # npm: no user config, no global cache reuse, no update notifier.
    env.update(
        {
            "npm_config_userconfig": os.devnull,
            "npm_config_globalconfig": os.devnull,
            "npm_config_cache": str(temp_dir / "npm"),
            "NO_UPDATE_NOTIFIER": "1",
        }
    )
    return env


def _dispatch_subprocess(spec: dict, classification: dict, script: str) -> dict:
    """Route to the right runtime's subprocess runner based on classification.

    The caller (`run()`) has already enforced via `_unsupported_runtime_reason`
    that classification['runtime'] is in `_SUPPORTED_RUNTIMES`. If a future
    runtime slips through unguarded, we return a clear error rather than
    crashing on a KeyError.
    """
    runtime = classification.get("runtime", "python")
    if runtime == "python":
        return _run_subprocess_python(spec, classification, script)
    if runtime == "node":
        return _run_subprocess_node(spec, classification, script)
    if runtime == "huggingface":
        return _run_subprocess_hf(spec, classification, script)
    # Belt-and-braces — should never hit, since the pre-flight gate rejects
    # unknown runtimes before we ever generate a script.
    start = datetime.now()
    return _result(
        start, -1, "",
        f"unsupported runtime {runtime!r} reached dispatcher (should be impossible)",
        stage="install",
    )


def _run_subprocess_python(spec: dict, classification: dict, script: str) -> dict:
    """pip install the tool into a venv-less tempdir target, then run the
    generated test with a minimal env. Returns a dict the interpreter can
    reason about."""
    package = classification.get("package") or spec.get("package") or spec["name"]
    start = datetime.now()
    with tempfile.TemporaryDirectory(prefix="ai-lab-py-") as td:
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
                env=_neutralised_env(tdp),
                cwd=str(tdp),
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
        # NO API token, NO repo token — it physically cannot call any
        # paid API, so it can't burn quota and can't exfil secrets.
        # HOME is the temp dir so the child cannot read real ~/.aws,
        # ~/.ssh, ~/.config/pip, etc.
        run_env = {
            **_hermetic_base_env(temp_home=tdp),
            "PYTHONPATH":     str(target),
            "PYTHONIOENCODING": "utf-8",
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


def _run_subprocess_node(spec: dict, classification: dict, script: str) -> dict:
    """`npm install --prefix <tmpdir>` then run the generated JS test with a
    minimal env. Same hermetic guarantees as the Python path — no API keys,
    no tokens reach the child."""
    package = classification.get("package") or spec.get("package") or spec["name"]
    start = datetime.now()
    with tempfile.TemporaryDirectory(prefix="ai-lab-node-") as td:
        tdp = Path(td)
        script_path = tdp / "lab_test.js"
        script_path.write_text(script)

        # `npm install --prefix <tdp>` lands modules under <tdp>/node_modules.
        # We do NOT pass --global, do NOT touch the runner's npm cache beyond
        # what the runner caches at the pipeline level.
        install_cmd = [
            "npm", "install",
            "--prefix", str(tdp),
            "--no-audit", "--no-fund",
            "--loglevel", "error",
            package,
        ]
        try:
            install_proc = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                env=_neutralised_env(tdp),
                cwd=str(tdp),
            )
        except subprocess.TimeoutExpired:
            return _result(start, -1, "", f"npm install timed out after {SUBPROCESS_TIMEOUT}s")
        except FileNotFoundError:
            return _result(
                start, -1, "",
                "npm not found on PATH — the pipeline image needs `apt-get install nodejs npm`. "
                "If you're running locally, install Node 20+.",
                stage="install",
            )

        if install_proc.returncode != 0:
            return _result(
                start, install_proc.returncode,
                install_proc.stdout[-2000:],
                f"npm install failed:\n{install_proc.stderr[-2000:]}",
                stage="install",
            )

        run_env = {
            **_hermetic_base_env(temp_home=tdp),
            "NODE_PATH":          str(tdp / "node_modules"),
            "NO_UPDATE_NOTIFIER": "1",
            "npm_config_loglevel": "error",
            "npm_config_userconfig": os.devnull,
            "npm_config_cache":      str(tdp / "npm"),
        }
        try:
            run_proc = subprocess.run(
                ["node", str(script_path)],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                env=run_env,
                cwd=str(tdp),
            )
        except subprocess.TimeoutExpired:
            return _result(
                start, -1, "",
                f"node script timed out after {SUBPROCESS_TIMEOUT}s wall clock",
                stage="run",
            )

        return _result(
            start,
            run_proc.returncode,
            run_proc.stdout[-4000:],
            run_proc.stderr[-4000:],
            stage="run",
        )


def _run_subprocess_hf(spec: dict, classification: dict, script: str) -> dict:
    """HuggingFace runtime — pip-installs `huggingface_hub` + `transformers`
    (no torch) into a tempdir target, then runs the generated Python script
    that loads config + tokenizer only. Weights are NOT downloaded; the
    pre-flight `_unsupported_runtime_reason` already rejected models whose
    total weight files exceed `_HF_MODEL_SIZE_CAP_GB`."""
    start = datetime.now()
    with tempfile.TemporaryDirectory(prefix="ai-lab-hf-") as td:
        tdp = Path(td)
        target = tdp / "pkg"
        target.mkdir()
        script_path = tdp / "lab_test.py"
        script_path.write_text(script)

        # huggingface_hub is light (~3MB). transformers without torch is ~80MB
        # — bigger than typical pip installs but still fits in the pipeline
        # disk + pip cache. NO torch on purpose: we don't run inference.
        install_cmd = [
            sys.executable, "-m", "pip", "install",
            "--quiet",
            "--target", str(target),
            "--disable-pip-version-check",
            "--no-input",
            "huggingface_hub", "transformers",
        ]
        try:
            install_proc = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                env=_neutralised_env(tdp),
                cwd=str(tdp),
            )
        except subprocess.TimeoutExpired:
            return _result(start, -1, "", f"pip install (huggingface_hub + transformers) timed out after {SUBPROCESS_TIMEOUT}s")

        if install_proc.returncode != 0:
            return _result(
                start, install_proc.returncode,
                install_proc.stdout[-2000:],
                f"HF runtime install failed:\n{install_proc.stderr[-2000:]}",
                stage="install",
            )

        run_env = {
            **_hermetic_base_env(temp_home=tdp),
            "PYTHONPATH":     str(target),
            "PYTHONIOENCODING": "utf-8",
            # Force HF cache under tempdir so it dies with the container.
            "HF_HOME":         str(tdp / "hf_cache"),
            # Hard belt: refuse to use any HF token even if one leaked in.
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "TRANSFORMERS_OFFLINE": "0",  # we DO need network for from_pretrained
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
                start, -1, "",
                f"HF test script timed out after {SUBPROCESS_TIMEOUT}s wall clock",
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
    "description": "Interpret the lab run and emit structured local insights.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One sentence: would this be useful for team?"},
            "verdict_for_team": {"type": "string", "enum": ["worth_trial", "monitor", "skip"]},
            "what_worked": {"type": "string", "description": "1–2 sentences on what the script confirmed."},
            "what_didnt": {"type": "string", "description": "1–2 sentences on what failed or was unclear (or 'nothing — clean run')."},
            "next_step": {"type": "string", "description": "Concrete recommendation, e.g. 'lab <tool>' or 'add to tech-radar at TRIAL' or 'no further action'."},
            "test_quality_self_rating": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["headline", "verdict_for_team", "what_worked", "what_didnt", "next_step", "test_quality_self_rating"],
    },
}


def _interpret(client, spec: dict, classification: dict, script: str, sandbox: dict) -> tuple[dict, float]:
    model_id = client.model(FAST)
    runtime = classification.get("runtime", "python")
    user_msg = (
        f"Tool: {spec['name']}\nCategory: {classification.get('category')}\n"
        f"Runtime: {runtime}\n"
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
        model=model_id,
        max_tokens=MAX_TOKENS_PER_CALL,
        system=[{"type": "text", "text": (
            "You are Frontier Scout's lab interpreter. Given a sandbox run, "
            "emit structured insights for the team. Be terse, team-specific, "
            "and HONEST about confidence. The lab supports three runtimes "
            "(python / node / huggingface) and the runtime name appears in "
            "the user message — use it to recognise runtime-typical failure "
            "modes (e.g. `npm install` 404, `from_pretrained` gated, native "
            "build errors). Recommendations should be concise and concrete "
            "('install fine, basic API works' / 'install ok but heavy deps' / "
            "'install failed: native build')."
        )}],
        tools=[_INTERPRET_TOOL],
        tool_choice={"type": "tool", "name": "emit_lab_insights"},
        messages=[{"role": "user", "content": user_msg}],
    )
    cost = log_call("lab-interpret", getattr(resp, "model", None) or model_id, resp.usage)
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return dict(tool_use.input), cost


# ── Step 7: format local lab summary + write transcript ─────────────────────

# ── Test-script excerpt extraction (Round 8) ─────────────────────────────────

def _test_excerpt(test_script: str, max_lines: int = 6) -> str:
    """Pull a small representative excerpt from the generated test script
    for the lab reply's `rich_text_preformatted` code block. Skips the
    file-level docstring + leading comments + blank lines, then takes the
    first `max_lines` of actual code. Keeps the reply tight (≤6 lines)
    and proves the test really ran rather than just claiming it did.

    Handles both single-line (`\"\"\"foo\"\"\"`) and multi-line docstrings.
    """
    if not test_script:
        return ""
    lines = test_script.splitlines()
    out: list[str] = []
    in_docstring = False
    docstring_open = ""
    started = False

    for line in lines:
        if in_docstring:
            # End of multi-line docstring on this line?
            if docstring_open in line:
                in_docstring = False
            continue

        # Detect docstring start (single-line OR multi-line opener)
        is_docstring_line = False
        for opener in ('"""', "'''"):
            count = line.count(opener)
            if count >= 2:
                # Single-line docstring: skip the whole line.
                is_docstring_line = True
                break
            if count == 1:
                # Multi-line docstring opens here; skip subsequent lines.
                in_docstring = True
                docstring_open = opener
                is_docstring_line = True
                break
        if is_docstring_line:
            continue

        stripped = line.strip()

        # Before we've found a real code line, skip blanks + comment-only lines.
        if not started:
            if not stripped or stripped.startswith("#"):
                continue
            started = True

        out.append(line)
        if len(out) >= max_lines:
            break

    return "\n".join(out)


# ── Step 7: print the structured lab summary ────────────────────────────────

def _post_lab_reply(
    *,
    tool: str,
    url: str,
    classification: dict,
    sandbox: dict,
    insights: dict,
    cost: float,
    test_excerpt: str,
    dry_run: bool,
) -> None:
    """Print the lab result in a compact local summary."""

    pill = {
        "worth_trial": "worth a TRIAL",
        "monitor":     "MONITOR",
        "skip":        "SKIP",
    }.get((insights or {}).get("verdict_for_team", ""), "MONITOR")
    print("─── Frontier Scout lab summary ───")
    print(f"Tool: {tool}")
    print(f"Source: {url}")
    print(f"Verdict: {pill}")
    if headline := (insights or {}).get("headline"):
        print(f"Headline: {headline}")
    if next_step := (insights or {}).get("next_step"):
        print(f"Next step: {next_step}")
    print(f"Runtime: {classification.get('runtime')} · exit={sandbox.get('exit_code')} · cost=${cost:.4f}")
    if test_excerpt:
        print("Test excerpt:")
        print(test_excerpt)
    print("─── END ───")


def _post_thread_if_possible(tool: str, text: str, dry_run: bool) -> None:
    """Print a local one-line lab status message."""
    prefix = "DRY-RUN" if dry_run else "LAB"
    print(f"{prefix}: {tool}: {text}")


def _write_transcript(
    tool: str, url: str, user: str,
    classification: dict | None, script: str,
    sandbox: dict | None, insights: dict | None,
) -> Path:
    LABS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", tool.lower()).strip("-") or "unknown"
    path = LABS_DIR / f"{today}-{slug}.md"
    body = (
        f"# Lab transcript: {tool}\n\n"
        f"_Ran by {user or 'local user'} on {today} via the Frontier Scout lab._\n\n"
        f"Source: {url}\n\n"
        f"## Classification\n```json\n{json.dumps(classification, indent=2)}\n```\n\n"
        f"## Generated test script\n```python\n{script}\n```\n\n"
        f"## Sandbox result\n```json\n{json.dumps(sandbox or {}, indent=2)}\n```\n\n"
        f"## Insights\n```json\n{json.dumps(insights or {}, indent=2)}\n```\n"
    )
    path.write_text(body)
    json_path = path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "tool": tool,
                "url": url,
                "user": user or "local user",
                "classification": classification or {},
                "sandbox": sandbox or {},
                "insights": insights or {},
                "transcript_path": str(path),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"  Transcript → {path}")
    print(f"  Structured result → {json_path}")
    return path


# ── Misc helpers ─────────────────────────────────────────────────────────────

def _provider():
    """Resolve the active LLM backend for a lab run."""
    return resolve_provider()


if __name__ == "__main__":
    sys.exit(main())
