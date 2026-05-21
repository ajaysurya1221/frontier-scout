"""
Slack request signature verification (Slack's HMAC-SHA256 scheme).

https://api.slack.com/authentication/verifying-requests-from-slack

The Lambda Function URL is a public HTTPS endpoint. Anyone on the internet
can POST to it. We MUST verify every request actually originates from
Slack before doing anything else — otherwise an attacker can impersonate
a Slack workflow and trigger arbitrary Bitbucket pipelines.

Verification:
  1. Slack sends headers:
       X-Slack-Request-Timestamp: <unix epoch>
       X-Slack-Signature: v0=<hmac_sha256 of "v0:<ts>:<body>" using signing-secret>
  2. Build the expected signature ourselves; compare in constant time.
  3. Reject if timestamp is > 5 minutes old (replay defense).
"""

from __future__ import annotations

import hashlib
import hmac
import time


REPLAY_WINDOW_SECONDS = 60 * 5  # 5 minutes per Slack guidance


def verify_slack_request(
    signing_secret: str,
    headers: dict,
    body: str,
    now: float | None = None,
) -> bool:
    """Return True iff the request signature is valid and not stale.

    `headers` must be lowercased dict (handler.py does this).
    `body` must be the raw request body string (handler.py decodes base64).
    """
    if not signing_secret:
        return False

    ts = headers.get("x-slack-request-timestamp")
    sig = headers.get("x-slack-signature")
    if not ts or not sig:
        return False

    # Replay-attack guard: reject anything more than 5 minutes old.
    current = now if now is not None else time.time()
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(current - ts_int) > REPLAY_WINDOW_SECONDS:
        return False

    basestring = f"v0:{ts}:{body}".encode("utf-8")
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            basestring,
            hashlib.sha256,
        ).hexdigest()
    )

    # Constant-time comparison — never use == here.
    return hmac.compare_digest(expected, sig)
