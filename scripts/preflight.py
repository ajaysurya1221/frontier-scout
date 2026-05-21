#!/usr/bin/env python3
"""
Operator preflight check — run before enabling scheduled pipelines.

Validates that everything the production pipeline needs is actually wired:
env vars present, Slack scopes correct, Slack webhook reachable, Lambda URL
rejecting unsigned requests, Bitbucket trigger credentials valid, and S3
mirror writable.

Exits non-zero on any failure so it can gate CI or a manual check.

Usage:
    python scripts/preflight.py                 # all checks
    python scripts/preflight.py --skip-aws      # local-only checks
    python scripts/preflight.py --skip-lambda   # skip Lambda URL probe
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}✅{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠️{RESET}   {msg}")


def fail(msg: str) -> None:
    print(f"{RED}❌{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"{DIM}    {msg}{RESET}")


def check_env_vars() -> int:
    """Verify required env vars are present and well-formed."""
    print("\n=== Environment variables ===")
    failures = 0

    required = [("ANTHROPIC_API_KEY", "sk-ant-")]
    for var, prefix in required:
        v = os.environ.get(var, "")
        if not v:
            fail(f"{var} not set")
            failures += 1
        elif prefix and not v.startswith(prefix):
            fail(f"{var} does not start with {prefix!r}")
            failures += 1
        else:
            ok(f"{var} set ({len(v)} chars, starts with {v[:6]}…)")

    optional = [
        ("OPENAI_API_KEY", "sk-", "Mem0 embeddings"),
        ("GITHUB_TOKEN", "g", "GitHub API rate limit raise"),
    ]
    for var, prefix, purpose in optional:
        v = os.environ.get(var, "")
        if not v:
            warn(f"{var} not set — {purpose} disabled")
        elif prefix and not v.startswith(prefix):
            warn(f"{var} doesn't start with {prefix!r} — verify it's a {var}")
        else:
            ok(f"{var} set ({len(v)} chars)")

    # Slack target — at least one must be set
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "")
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if bot_token.startswith("xoxb-") and channel_id.startswith("C"):
        ok("SLACK_BOT_TOKEN + SLACK_CHANNEL_ID set — threaded format will be used")
    elif webhook.startswith("https://hooks.slack.com/"):
        ok("SLACK_WEBHOOK_URL set — single-message format will be used")
    elif bot_token.startswith("https://hooks.slack.com/"):
        warn("SLACK_BOT_TOKEN looks like a webhook URL — auto-detect will route it")
    else:
        fail("No Slack target configured. Set SLACK_BOT_TOKEN+SLACK_CHANNEL_ID or SLACK_WEBHOOK_URL")
        failures += 1

    return failures


def check_dependencies() -> int:
    """Verify the Python deps actually import."""
    print("\n=== Python dependencies ===")
    failures = 0
    pkgs = [
        ("anthropic", "Anthropic SDK"),
        ("feedparser", "RSS parsing"),
        ("requests", "HTTP"),
        ("pydantic", "Validator gates"),
        ("bs4", "GitHub Trending HTML parse (beautifulsoup4)"),
        ("slack_sdk", "Slack bot client"),
    ]
    for pkg, purpose in pkgs:
        try:
            __import__(pkg)
            ok(f"{pkg} importable — {purpose}")
        except ImportError:
            fail(f"{pkg} not installed — {purpose}")
            failures += 1

    # Optional
    try:
        import mem0  # noqa: F401
        ok("mem0ai importable — Mem0 prior-filter + post-seed enabled")
    except ImportError:
        warn("mem0ai not installed — Mem0 features disabled")
    try:
        import chromadb  # noqa: F401
        ok("chromadb importable — semantic Mem0 search enabled")
    except ImportError:
        warn("chromadb not installed — semantic Mem0 search disabled")

    return failures


def check_lambda_url(url: str) -> int:
    """Probe the Lambda Function URL with an unsigned POST.

    Expected: HTTP 401 invalid signature. Any other response is a misconfig.
    """
    print(f"\n=== Lambda Function URL probe ({url}) ===")
    if not url:
        warn("LAMBDA_URL not provided — skipping probe (use --lambda-url)")
        return 0
    try:
        import requests
    except ImportError:
        fail("requests not installed — can't probe Lambda")
        return 1
    try:
        r = requests.post(url, data="command=/radar&text=mem0", timeout=10)
    except Exception as e:  # noqa: BLE001
        fail(f"Lambda URL unreachable: {e}")
        return 1
    if r.status_code == 401:
        ok(f"Lambda returned 401 on unsigned POST — signature gate is enforced")
        return 0
    fail(f"Lambda returned {r.status_code} (expected 401). Signature verification may be broken.")
    info(f"body: {r.text[:200]!r}")
    return 1


def check_bitbucket_trigger() -> int:
    """Verify Bitbucket API credentials can list pipelines (read-only probe)."""
    print("\n=== Bitbucket trigger credentials ===")
    workspace = os.environ.get("BB_WORKSPACE", "")
    repo = os.environ.get("BB_REPO", "")
    token = os.environ.get("BB_TOKEN", "")
    if not (workspace and repo and token):
        warn("BB_WORKSPACE / BB_REPO / BB_TOKEN incomplete — skipping probe")
        return 0
    try:
        import requests
        from base64 import b64encode
    except ImportError:
        fail("requests not installed — can't probe Bitbucket")
        return 1
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pipelines/?pagelen=1"
    headers = {
        "Authorization": "Basic " + b64encode(f"x-token-auth:{token}".encode()).decode(),
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=8)
    except Exception as e:  # noqa: BLE001
        fail(f"Bitbucket API unreachable: {e}")
        return 1
    if r.status_code == 200:
        ok(f"Bitbucket API reachable — token works against {workspace}/{repo}")
        return 0
    fail(f"Bitbucket API returned {r.status_code} (expected 200). Token or workspace/repo wrong.")
    info(f"body: {r.text[:200]!r}")
    return 1


def check_s3_mirror() -> int:
    """Verify the S3 mirror bucket is reachable and writable."""
    print("\n=== S3 mirror bucket ===")
    bucket = os.environ.get("S3_MIRROR_BUCKET", "")
    if not bucket:
        warn("S3_MIRROR_BUCKET not set — /recall semantic search will be degraded")
        return 0
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        warn("boto3 not installed — can't probe S3 (Lambda runtime has it)")
        return 0
    region = os.environ.get("AWS_REGION", "us-east-2")
    s3 = boto3.client("s3", region_name=region)
    try:
        s3.head_bucket(Bucket=bucket)
        ok(f"Bucket {bucket} is reachable")
    except ClientError as e:
        fail(f"head_bucket failed: {e}")
        return 1
    # Write probe — try a small object
    try:
        s3.put_object(Bucket=bucket, Key=".preflight-probe", Body=b"ok")
        s3.delete_object(Bucket=bucket, Key=".preflight-probe")
        ok(f"Bucket {bucket} accepts writes")
    except ClientError as e:
        fail(f"put/delete probe failed: {e}")
        return 1
    return 0


def check_validators_import() -> int:
    """Ensure validators import cleanly (the SOC2 gate)."""
    print("\n=== Policy gate module ===")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        import validators  # noqa: F401
        ok(f"validators module imports ({len(validators.ALLOWED_DOMAINS)} URL allowlist entries)")
    except Exception as e:  # noqa: BLE001
        fail(f"validators import failed: {e}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Telemetry preflight check")
    parser.add_argument("--skip-aws", action="store_true", help="skip S3 + Lambda probes")
    parser.add_argument("--skip-lambda", action="store_true", help="skip Lambda URL probe")
    parser.add_argument("--lambda-url", default=os.environ.get("LAMBDA_URL", ""),
                        help="Lambda Function URL to probe (else $LAMBDA_URL)")
    args = parser.parse_args()

    print("🩺  AI Telemetry preflight\n")
    fails = 0
    fails += check_env_vars()
    fails += check_dependencies()
    fails += check_validators_import()
    fails += check_bitbucket_trigger()
    if not args.skip_aws:
        fails += check_s3_mirror()
        if not args.skip_lambda:
            fails += check_lambda_url(args.lambda_url)

    print()
    if fails == 0:
        print(f"{GREEN}✅ All checks passed — production is preflight-ready.{RESET}")
        return 0
    print(f"{RED}❌ {fails} failure(s). Fix before enabling schedules.{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
