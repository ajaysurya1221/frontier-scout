"""
Slack App Home dispatcher — handles `app_home_opened` events.

When a user clicks the bot's profile and lands on the Home tab, Slack
fires an `app_home_opened` event. We rebuild the dashboard view from
the latest mirror state and publish it via `views.publish`.

Refresh model:
  • On every Home-tab open. Slack does the work; no cron, no buttons.
  • Pure file-read + JSON-build inside Lambda — typical ~10ms.
  • Zero LLM cost. Zero new Slack scopes (uses existing `chat:write`).

Data sources (read-only via the Lambda github-mirror):
  • preferences.json            — channel taste-model snapshot
  • costs.jsonl                  — month-to-date spend + per-day trend
  • quality-log.jsonl            — verdicts shipped per recent Scout run
  • briefings/<latest>.md         — most recent briefing summary
  • briefings/<latest>-meta.json  — message ts for the briefing link
  • .scratch/labs/<recent>.md     — recent lab transcripts (3 most recent)

If the mirror is unavailable, the dispatcher publishes the cold-start
view rather than erroring out.

Trust boundary:
  • Read-only from the mirror; never writes back.
  • Publishes ONLY to the requesting user's home (per Slack's
    views.publish contract — `user_id` is the recipient).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


def handle(body: dict) -> dict:
    """Dispatch an `app_home_opened` event_callback.

    Slack envelope:
      {"type": "event_callback",
       "event": {"type": "app_home_opened", "user": "U0…", "tab": "home", ...}}

    Returns a 200-OK shaped response. Any internal failure is logged
    and ACKed — never let the Lambda crash out from a single user's
    home open.
    """
    event = body.get("event") or {}
    if event.get("type") != "app_home_opened":
        return _ack()
    # Slack also fires this event for the "messages" tab; ignore those.
    if event.get("tab") and event.get("tab") != "home":
        return _ack()

    user_id = event.get("user", "")
    if not user_id:
        print("  app_home_opened: missing user_id — skipping publish")
        return _ack()

    state = _collect_state()
    try:
        from home_view import build_view
    except Exception as e:  # noqa: BLE001
        print(f"  home_view import failed: {e} — publishing minimal placeholder")
        view = {"type": "home", "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
                "text": "*Frontier Scout* — dashboard temporarily unavailable."}},
        ]}
    else:
        try:
            view = build_view(state)
        except Exception as e:  # noqa: BLE001
            print(f"  build_view crashed: {e} — publishing placeholder")
            view = {"type": "home", "blocks": [
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": "*Frontier Scout* — dashboard render failed. "
                            "Check Lambda logs for details."}},
            ]}

    _publish_home_view(user_id, view)
    return _ack()


# ── State collection (read-only via the existing github mirror) ───────────

def _collect_state() -> dict:
    """Walk the Lambda's github-mirror and assemble the dashboard state
    dict. Every step is wrapped in try/except so missing data degrades
    to a graceful placeholder rather than crashing the publish."""
    state: dict = {}

    # Make sure the mirror is fresh (10-min TTL is fine for the App Home).
    try:
        import radar_query
        radar_query._ensure_mirror()
        mirror = radar_query.LOCAL_MIRROR
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: mirror unavailable: {e}")
        return state

    # 1. Channel taste model (preferences.json).
    try:
        prefs_path = mirror / "preferences.json"
        if prefs_path.exists():
            state["preferences"] = json.loads(prefs_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: preferences read failed: {e}")

    # 2. MTD cost + per-day cost trend (costs.jsonl).
    try:
        costs_path = mirror / "costs.jsonl"
        if costs_path.exists():
            mtd, per_day = _read_costs(costs_path)
            state["mtd_cost"] = mtd
            state["cost_per_day_mtd"] = per_day
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: costs read failed: {e}")

    # 3. Verdict counts per Scout run from quality-log.jsonl.
    try:
        ql_path = mirror / "quality-log.jsonl"
        if ql_path.exists():
            history, this_week = _read_quality_log(ql_path)
            state["verdicts_per_week"] = history
            state["verdicts_this_week"] = this_week
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: quality-log read failed: {e}")

    # 4. Latest briefing summary.
    try:
        bdir = mirror / "briefings"
        if bdir.exists():
            state["latest_briefing"] = _latest_briefing(bdir)
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: latest briefing read failed: {e}")

    # 5. Recent lab transcripts.
    try:
        labs_dir = mirror / ".scratch" / "labs"
        if labs_dir.exists():
            state["recent_labs"] = _recent_labs(labs_dir)
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: recent labs read failed: {e}")

    # 6. Last Scout run timestamp from quality-log.jsonl tail.
    try:
        ql_path = mirror / "quality-log.jsonl"
        if ql_path.exists():
            state["last_scout_run_at"] = _last_scout_run_ts(ql_path)
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: last-scout-run read failed: {e}")

    # 7. Static-ish metadata.
    state["next_scout_at_label"] = "Monday 03:30 UTC"
    state["lambda_commit"] = os.environ.get("GITHUB_SHA", "")[:12]
    state["lambda_branch"] = os.environ.get("GITHUB_REF_NAME", "main")

    return state


def _read_costs(costs_path: Path) -> tuple[float, list[float]]:
    """Compute MTD total + per-day total for the last 14 days."""
    today = datetime.now(timezone.utc)
    month_prefix = today.strftime("%Y-%m")
    by_day: dict[str, float] = {}
    mtd_total = 0.0
    for line in costs_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("ts", "")
        if not ts.startswith(month_prefix):
            continue
        day = ts[:10]  # YYYY-MM-DD
        usd = float(rec.get("cost_usd", 0) or 0)
        by_day[day] = by_day.get(day, 0.0) + usd
        mtd_total += usd
    # Build last-14-days series ending today
    series: list[float] = []
    for i in range(13, -1, -1):
        d = (today - _timedelta(days=i)).strftime("%Y-%m-%d")
        series.append(by_day.get(d, 0.0))
    return round(mtd_total, 4), series


def _read_quality_log(ql_path: Path) -> tuple[list[int], int]:
    """Per-week verdict counts (last 8 weeks) + this-week count."""
    today = datetime.now(timezone.utc)
    iso_year_week_now = today.isocalendar()[:2]
    by_week: dict[tuple[int, int], int] = {}
    for line in ql_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("component") != "scout":
            continue
        ts = rec.get("ts", "")
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        yw = d.isocalendar()[:2]
        by_week[yw] = by_week.get(yw, 0) + int(rec.get("verdicts_post_judge", 0) or 0)
    # Build series for the LAST 8 ISO weeks ending this week
    series: list[int] = []
    for offset in range(7, -1, -1):
        delta = _timedelta(weeks=offset)
        d = today - delta
        yw = d.isocalendar()[:2]
        series.append(by_week.get(yw, 0))
    this_week = by_week.get(iso_year_week_now, 0)
    return series, this_week


def _latest_briefing(bdir: Path) -> dict | None:
    """Read the most recent briefing's markdown + meta sidecar."""
    mds = sorted(
        (p for p in bdir.glob("*.md") if not p.name.endswith("-meta.md")),
        reverse=True,
    )
    if not mds:
        return None
    latest = mds[0]
    date = latest.stem
    text = latest.read_text(errors="ignore")
    # Verdict count = count of `### ` markdown headers
    verdicts_count = sum(1 for line in text.splitlines() if line.startswith("### "))
    # Judge confidence + summary from the briefing header (Scout writes
    # "Judge confidence: **HIGH**." and a blockquote with the summary)
    rating = "medium"
    m = re.search(r"[Jj]udge confidence:\s*\*\*([A-Za-z]+)\*\*", text)
    if m:
        rating = m.group(1).lower()
    summary = ""
    m = re.search(r"^>\s*_(.+?)_\s*$", text, re.MULTILINE)
    if m:
        summary = m.group(1).strip()
    # Permalink: read meta sidecar for the parent_ts and construct a
    # Slack-style archive link if we have channel ID.
    permalink = ""
    meta_path = bdir / f"{date}-meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            parent_ts = meta.get("parent_ts", "")
            channel = os.environ.get("SLACK_CHANNEL_ID", "")
            if parent_ts and channel:
                # Slack permalink format: slack://channel?team=…&id=… is not
                # universally clickable. Web-archive URL works everywhere:
                #   https://<workspace>.slack.com/archives/<channel>/p<ts-without-dot>
                # We don't know the workspace slug from env; fall back to
                # `slack://channel?id=…` which the Slack client resolves.
                ts_part = parent_ts.replace(".", "")
                permalink = (
                    f"slack://channel?team=&id={channel}&message={ts_part}"
                )
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "date": date,
        "verdicts_count": verdicts_count,
        "judge_rating": rating,
        "judge_summary": summary[:200],
        "permalink": permalink,
    }


def _recent_labs(labs_dir: Path, limit: int = 3) -> list[dict]:
    """Pull the N most recent lab transcripts."""
    paths = sorted(labs_dir.glob("*.md"), reverse=True)[:limit]
    out: list[dict] = []
    for p in paths:
        text = p.read_text(errors="ignore")
        tool = ""
        rec = "monitor"
        # Tool name: title line `# Lab transcript: <tool>` (round 7 format)
        m = re.search(r"^#\s*Lab transcript:\s*(.+)$", text, re.MULTILINE)
        if m:
            tool = m.group(1).strip()
        # Recommendation pulled from the JSON insights block
        m = re.search(r'"verdict_for_team":\s*"([a-z_]+)"', text)
        if m:
            rec = m.group(1)
        # Date from the filename prefix YYYY-MM-DD-<slug>.md
        ran_at = ""
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", p.stem)
        if m:
            ran_at = m.group(1) + "T00:00:00Z"
        out.append({
            "tool": tool or p.stem,
            "verdict_for_team": rec,
            "ran_at": ran_at,
        })
    return out


def _last_scout_run_ts(ql_path: Path) -> str:
    """Return the ts of the most recent `component: scout` row."""
    last_ts = ""
    for line in ql_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("component") == "scout":
            ts = rec.get("ts", "")
            if ts > last_ts:
                last_ts = ts
    return last_ts


# ── Slack views.publish call ─────────────────────────────────────────────────

def _publish_home_view(user_id: str, view: dict) -> None:
    """POST to Slack's views.publish endpoint with the home view."""
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not bot_token.startswith("xoxb-"):
        print("  app_home: SLACK_BOT_TOKEN missing or wrong shape — skipping publish")
        return

    payload = json.dumps({"user_id": user_id, "view": view}).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/views.publish",
        data=payload,
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            body_bytes = resp.read()
            data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
        if not data.get("ok"):
            print(f"  app_home: views.publish returned {data.get('error')!r}")
        else:
            print(f"  app_home: published to {user_id}")
    except urllib.error.HTTPError as e:
        body_preview = e.read().decode("utf-8", errors="ignore")[:200]
        print(f"  app_home: views.publish HTTP {e.code}: {body_preview}")
    except Exception as e:  # noqa: BLE001
        print(f"  app_home: views.publish failed: {e}")


# ── Small helpers ────────────────────────────────────────────────────────────

def _ack() -> dict:
    return {"statusCode": 200, "body": ""}


def _timedelta(**kwargs):
    """Tiny shim to avoid a top-level import (saves Lambda cold-start)."""
    from datetime import timedelta
    return timedelta(**kwargs)
