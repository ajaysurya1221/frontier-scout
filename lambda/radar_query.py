"""
Slash command handlers — `/radar <tool>` and `/recall <topic>`.

Both query Mem0 (Chroma file-store mirrored from the GitHub repo or optional
S3 mirror). Lambda downloads the collection on cold start, caches it in /tmp,
and queries directly. If the mirror is unavailable, commands degrade to useful
ephemeral text rather than a Slack error.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

LOCAL_MIRROR = Path("/tmp/frontier-scout-mirror")
CHROMA_LOCAL = LOCAL_MIRROR / "memory" / "chroma"
RADAR_LOCAL = LOCAL_MIRROR / "tech-radar.md"

# Hard caps for the S3 mirror sync — defense against a misconfigured or
# malicious mirror trying to fill /tmp (Lambda has 512MB ephemeral by default).
MAX_MIRROR_BYTES = 200 * 1024 * 1024   # 200 MB cap; comfortably above expected
MAX_MIRROR_OBJECTS = 5000              # cap object count to prevent enumeration abuse


# ── Slack-shape responses ────────────────────────────────────────────────────

def _ephemeral(text: str, blocks: list[dict] | None = None) -> dict:
    payload: dict = {"response_type": "ephemeral", "text": text}
    if blocks:
        payload["blocks"] = blocks
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _in_channel(text: str, blocks: list[dict] | None = None) -> dict:
    payload: dict = {"response_type": "in_channel", "text": text}
    if blocks:
        payload["blocks"] = blocks
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


# ── Mirror sync (GitHub/S3 → /tmp) ───────────────────────────────────────────

def _ensure_mirror() -> bool:
    """Populate /tmp/frontier-scout-mirror/ from GitHub or optional S3.

    Routing:
      1. S3_MIRROR_BUCKET set → sync from S3 (legacy compatibility path).
      2. Otherwise → fetch the repo tarball from GitHub using GH_REPO and
         optional GH_TOKEN/GITHUB_TOKEN.

    Returns True if the mirror is usable after this call, False otherwise.
    """
    bucket = os.environ.get("S3_MIRROR_BUCKET")
    if not bucket:
        # Default: pull from GitHub, the repo's single source of truth.
        try:
            from github_mirror import ensure_mirror_from_github
            return ensure_mirror_from_github()
        except ImportError as e:
            print(f"  github_mirror unavailable: {e}")
            return False

    if (LOCAL_MIRROR / ".synced").exists():
        return True
    try:
        import boto3  # type: ignore
    except ImportError:
        print("boto3 not bundled in Lambda zip — S3 mirror unavailable")
        return False
    prefix = os.environ.get("S3_MIRROR_PREFIX", "").lstrip("/")
    s3 = boto3.client("s3")
    LOCAL_MIRROR.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    total_bytes = 0
    total_objects = 0
    mirror_root = LOCAL_MIRROR.resolve()

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            size = obj.get("Size", 0) or 0
            relative = key[len(prefix):].lstrip("/")
            if not relative:
                continue

            # Path-traversal guard: the resolved destination MUST live under
            # the mirror root. A key like `../../etc/passwd` would resolve
            # outside the root and gets rejected here.
            candidate = (LOCAL_MIRROR / relative).resolve()
            try:
                candidate.relative_to(mirror_root)
            except ValueError:
                print(f"  ⛔ rejected mirror key (path traversal): {key!r}")
                continue

            # Size caps: object count + cumulative bytes.
            total_objects += 1
            total_bytes += size
            if total_objects > MAX_MIRROR_OBJECTS:
                print(f"  ⛔ mirror object cap hit ({MAX_MIRROR_OBJECTS}); aborting sync")
                return False
            if total_bytes > MAX_MIRROR_BYTES:
                print(f"  ⛔ mirror byte cap hit ({MAX_MIRROR_BYTES} bytes); aborting sync")
                return False

            candidate.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(candidate))

    (LOCAL_MIRROR / ".synced").touch()
    return True


# ── /radar <tool> ────────────────────────────────────────────────────────────

def radar(tool: str, user_id: str) -> dict:
    """Look up the most recent verdict for `tool` in Mem0 / tech-radar."""
    tool = (tool or "").strip()
    if not tool:
        return _ephemeral(
            "Usage: `/radar <tool name>` — example: `/radar mem0`",
        )

    if not _ensure_mirror():
        return _ephemeral(
            ":warning: Radar mirror not configured. The operator needs to set "
            "`GH_REPO` on the Lambda, or configure `S3_MIRROR_BUCKET`. "
            "Falling back to tech-radar.md grep below.\n\n"
            + _grep_radar_fallback(tool)
        )

    # Try Mem0 first (semantic similarity over past verdicts)
    mem0_hit = _mem0_lookup(tool)
    if mem0_hit:
        return _ephemeral("", blocks=_format_radar_verdict(tool, mem0_hit))

    # Fall back to tech-radar.md grep
    radar_text = _grep_radar_fallback(tool)
    return _ephemeral(radar_text or f"No verdict found for *{tool}* on the radar.")


def _mem0_lookup(tool: str) -> dict | None:
    """Return the most-similar Mem0 entry for `tool`, or None."""
    try:
        # Mem0 + Chroma read-only access. We just need to query the Chroma DB
        # directly to avoid bringing in the full mem0ai dependency tree.
        import chromadb  # type: ignore
    except ImportError:
        print("chromadb not bundled — skipping semantic lookup")
        return None
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_LOCAL))
        coll = client.get_or_create_collection("ai_telemetry")
        # Chroma will embed the query if we pass `query_texts`. The Lambda needs
        # OPENAI_API_KEY for that to work; without it we fall back to no results.
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        results = coll.query(query_texts=[tool], n_results=1)
        ids = results.get("ids", [[]])[0]
        if not ids:
            return None
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return {
            "document": docs[0] if docs else "",
            "metadata": metas[0] if metas else {},
        }
    except Exception as e:  # noqa: BLE001
        print(f"Mem0/Chroma lookup failed: {e}")
        return None


def _grep_radar_fallback(tool: str) -> str:
    """If Mem0 is unavailable, grep tech-radar.md for the tool name."""
    if not RADAR_LOCAL.exists():
        return ""
    text = RADAR_LOCAL.read_text(errors="ignore")
    # Find the section/line containing the tool name (case-insensitive)
    pattern = re.compile(rf"^.*?\b{re.escape(tool)}\b.*$", re.I | re.M)
    hits = pattern.findall(text)
    if not hits:
        return ""
    snippet = "\n".join(hits[:6])
    return f":mag: Found in tech-radar.md:\n```\n{snippet}\n```"


def _format_radar_verdict(tool: str, hit: dict) -> list[dict]:
    """Render a Mem0 hit as Slack blocks."""
    meta = hit.get("metadata") or {}
    doc = (hit.get("document") or "").strip()
    verdict_emoji = {
        "adopt": "🟢", "trial": "🟡", "assess": "⚪", "hold": "🔴",
    }.get(meta.get("verdict", ""), "❔")
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{verdict_emoji}  *{tool}*  ·  "
                    f"verdict: *{(meta.get('verdict') or 'unknown').upper()}*  ·  "
                    f"SOC2: *{meta.get('soc2', 'unknown')}*  ·  "
                    f"category: *{meta.get('category', 'unknown')}*"
                ),
            },
        },
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"_Mem0 hit · added {meta.get('added_at', 'unknown')}_"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"```\n{doc[:1800]}\n```"}},
    ]


# ── /recall <topic> ──────────────────────────────────────────────────────────

def recall(topic: str, user_id: str) -> dict:
    """Semantic search over Mem0 — top N results inline."""
    topic = (topic or "").strip()
    if not topic:
        return _ephemeral("Usage: `/recall <topic>` — example: `/recall agent memory`")

    if not _ensure_mirror():
        return _ephemeral(":warning: Radar mirror not configured. Operator needs to set up S3 mirror.")

    try:
        import chromadb  # type: ignore
    except ImportError:
        return _ephemeral(":warning: Semantic search unavailable (chromadb not bundled).")

    if not os.environ.get("OPENAI_API_KEY"):
        return _ephemeral(":warning: Semantic search unavailable (OPENAI_API_KEY not set on Lambda).")

    try:
        client = chromadb.PersistentClient(path=str(CHROMA_LOCAL))
        coll = client.get_or_create_collection("ai_telemetry")
        results = coll.query(query_texts=[topic], n_results=5)
    except Exception as e:  # noqa: BLE001
        return _ephemeral(f":warning: Chroma query failed: {e}")

    ids = results.get("ids", [[]])[0]
    if not ids:
        return _ephemeral(f"No prior verdicts found related to *{topic}*.")

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":brain:  *Recall:* {topic}"}},
        {"type": "divider"},
    ]
    for doc, meta in zip(docs, metas):
        v = (meta or {}).get("verdict", "?")
        soc2 = (meta or {}).get("soc2", "?")
        tool = (meta or {}).get("tool", "?")
        emoji = {"adopt": "🟢", "trial": "🟡", "assess": "⚪", "hold": "🔴"}.get(v, "❔")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji}  *{tool}* — {v.upper()} · SOC2 {soc2}\n_{(doc or '')[:300]}_",
            },
        })
    return _ephemeral(f"Recall: {topic}", blocks=blocks)
