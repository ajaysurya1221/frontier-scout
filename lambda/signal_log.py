"""
Append Slack interaction signals to signals-log.jsonl via the GitHub REST API.

The ledger lives in the repo (committed, audit-tracked) and feeds the channel
taste model in scripts/preferences.py. Lambda calls append() whenever a user
reacts on a verdict card or clicks a button.

Implementation note: this is a simple read-modify-write through GitHub's
Contents API. That is acceptable for low-volume Slack feedback. If reaction
volume grows, move signal ingestion to a queued GitHub Actions workflow or a
small durable store with optimistic concurrency.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone


def append(
    *,
    signal: str,
    tool: str,
    category: str = "",
    tags: list[str] | None = None,
    user: str = "",
    message_ts: str = "",
    extra: dict | None = None,
) -> bool:
    """Append one signal line to signals-log.jsonl on GitHub.

    Returns True on success and False on any failure. A missed preference signal
    must never break the user-facing Slack path.
    """
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    branch = os.environ.get("GH_BRANCH") or os.environ.get("GITHUB_REF_NAME", "main")
    if not (repo and token):
        print("  signal_log: GH_REPO/GH_TOKEN missing — dropping signal")
        return False

    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "user": user,
        "signal": signal,
        "tool": tool,
        "category": category,
        "tags": [t.lower() for t in (tags or []) if isinstance(t, str) and t],
        "message_ts": message_ts,
    }
    if extra:
        record.update(extra)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)

    api_url = f"https://api.github.com/repos/{repo}/contents/signals-log.jsonl"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "frontier-scout-slack-lambda",
    }

    current = ""
    sha = None
    try:
        req = urllib.request.Request(f"{api_url}?ref={branch}", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        sha = payload.get("sha")
        encoded = payload.get("content", "")
        if encoded:
            current = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            body = e.read().decode("utf-8", errors="ignore")[:200]
            print(f"  signal_log: GET failed ({e.code}): {body}")
            return False
    except Exception as e:  # noqa: BLE001
        print(f"  signal_log: GET failed ({e}) — dropping signal")
        return False

    if current and not current.endswith("\n"):
        current += "\n"
    new_content = current + line + "\n"
    commit_msg = _clean_commit_message(f"signal: {signal} on {tool[:60]} by @{user or 'anon'}")
    body: dict = {
        "message": commit_msg,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
        "branch": branch,
        "committer": {
            "name": "Frontier Scout",
            "email": "frontier-scout@users.noreply.github.com",
        },
    }
    if sha:
        body["sha"] = sha

    try:
        req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
            if ok:
                print(f"  signal_log: committed {signal!r} for {tool!r}")
            else:
                print(f"  signal_log: PUT returned {resp.status}")
            return ok
    except urllib.error.HTTPError as e:
        body_preview = e.read().decode("utf-8", errors="ignore")[:200]
        print(f"  signal_log: PUT failed ({e.code}): {body_preview}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  signal_log: PUT failed: {e}")
        return False


def _clean_commit_message(value: str) -> str:
    """Keep Slack-controlled fields out of multi-line commit metadata."""
    return " ".join((value or "").replace("\r", " ").replace("\n", " ").split())
