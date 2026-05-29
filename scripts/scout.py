#!/usr/bin/env python3
"""Frontier Scout — weekly scan loop.

The CLI (`frontier-scout scan`) calls :func:`run_scan` once a week. The MCP
server never calls this directly — it only reads the SQLite store that this
loop writes to via the ``output_writer`` callback.

Pipeline:
    fetch (parallel)
      → dedupe by content hash
      → drop tools the user has seen via ``seen_check``
      → Sonnet score pass (0–10 + category)
      → Sonnet verdict pass (structured tool use)
      → optional Opus judge pass (gated by ``JUDGE_ENABLED``)
      → deterministic policy validators
      → ``output_writer`` callback (typically: persist to SQLite)

Env:
    ANTHROPIC_API_KEY    required for live scans
    GITHUB_TOKEN         optional — raises GitHub API rate limit 60→5000/hr
    JUDGE_ENABLED        ``false`` skips the Opus RLAIF judge (saves ~$0.20/scan)
    DRY_RUN              ``1`` → use fixture data only, no LLM calls
"""

from __future__ import annotations

import hashlib
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import feedparser
import judge as judge_mod
import quality_logger
import requests
from cost_tracker import log_call
from llm_client import STATS as LLM_STATS
from llm_client import call_with_retry
from tools import SCORE_ITEMS_TOOL, VERDICT_TOOL
from validators import validate_verdicts

from frontier_scout.providers import FAST, resolve_provider
from prompts import cached_system_blocks

# ── Config ──────────────────────────────────────────────────────────────────

# Historical default; the active model is whatever the resolved provider
# maps the "fast" tier to (Anthropic → claude-sonnet-4-6, OpenAI → gpt-4o-mini,
# CLI → the logged-in CLI's model).
MODEL = "claude-sonnet-4-6"
CUTOFF = datetime.now(UTC) - timedelta(days=7)

# Hard cap to bound worst-case scoring cost (Sonnet ~$0.20 at this cap).
MAX_ITEMS = 220

# Per-source-group quotas. Designed for the solo-AI-builder bullseye — heavy
# weight on the skill / MCP / agent-framework ecosystem, light on academia.
# Sums to <= MAX_ITEMS; remainder picked up by the round-robin redistribution
# in :func:`stratified_cap`.
SOURCE_QUOTAS = {
    "skills_release":   45,  # anthropics/skills + mattpocock/skills + peers
    "mcp_release":      35,  # MCP server registry + awesome-mcp-servers churn
    "claude_release":   20,  # Claude Code + plugins release notes
    "agent_release":    30,  # LangChain / LangGraph / CrewAI / Hermes / etc.
    "rss":              35,  # First-party labs + practitioner blogs
    "github_trending":  20,  # Python + TypeScript weekly
    "hf_trending":      15,  # HuggingFace likes-7d (with weight cap downstream)
    "hn_smart":         15,  # Algolia HN search (claude / mcp / agent / skill)
    "arxiv":             5,  # cs.AI recent — capped low; mostly noise for this audience
}
assert sum(SOURCE_QUOTAS.values()) <= MAX_ITEMS, "quotas exceed MAX_ITEMS"

USER_AGENT = "frontier-scout/0.1 (+https://github.com/ajaysurya1221/frontier-scout)"


# ── Source feed registry ────────────────────────────────────────────────────

# RSS feeds: first-party labs + practitioner blogs. Quota: "rss".
RSS_FEEDS: list[tuple[str, str]] = [
    ("Anthropic News",     "https://www.anthropic.com/news/rss.xml"),
    ("OpenAI Blog",        "https://openai.com/blog/rss.xml"),
    ("Google DeepMind",    "https://deepmind.google/blog/rss.xml"),
    ("Mistral News",       "https://mistral.ai/news/feed.xml"),
    ("Hugging Face Blog",  "https://huggingface.co/blog/feed.xml"),
    ("Simon Willison",     "https://simonwillison.net/atom/everything/"),
    ("Latent Space",       "https://www.latent.space/feed"),
    ("Eugene Yan",         "https://eugeneyan.com/rss/"),
    ("Ahead of AI",        "https://sebastianraschka.com/rss_feed.xml"),
    ("AI Tidbits",         "https://www.aitidbits.ai/feed"),
    ("Cameron Wolfe",      "https://cameronrwolfe.substack.com/feed"),
    ("HuggingFace Papers", "https://huggingface.co/papers/rss"),
    ("r/ClaudeAI",         "https://www.reddit.com/r/ClaudeAI/top.rss?t=week"),
    ("r/LocalLLaMA",       "https://www.reddit.com/r/LocalLLaMA/top.rss?t=week"),
    ("r/mcp",              "https://www.reddit.com/r/mcp/top.rss?t=week"),
]

def _pack_watchlist() -> list[tuple[str, str, str]]:
    from frontier_scout.packs import default_packs

    group_map = {
        "ai-devtools": "skills_release",
        "mcp": "mcp_release",
        "agent-frameworks": "agent_release",
        "local-ai": "agent_release",
        "rag-memory": "agent_release",
        "workflow-builders": "agent_release",
        "inference-gateway": "agent_release",
    }
    rows: list[tuple[str, str, str]] = [
        ("anthropics/skills", "anthropics/skills", "skills_release"),
        ("mattpocock/skills", "mattpocock/skills", "skills_release"),
        ("anthropics/claude-plugins-official", "Claude Code Plugins", "skills_release"),
    ]
    seen = {rows[0][0], rows[1][0], rows[2][0]}
    for slug, pack in default_packs().items():
        group = group_map.get(slug, "agent_release")
        for repo in pack.seed_repos:
            if repo not in seen:
                rows.append((repo, repo, group))
                seen.add(repo)
    return rows


# GitHub watchlist is generated from living pack seed repos. Packs can promote
# new candidates over time; these rows are only the bootloader.
GITHUB_WATCHLIST: list[tuple[str, str, str]] = _pack_watchlist()

# GitHub Trending — two languages to cover both ends of the stack.
TRENDING_LANGS = ["python", "typescript"]

# arXiv categories — capped low; this audience cares about applied tools, not papers.
ARXIV_CATS = ["cs.AI"]

# Smart HN keyword filter — tuned to skill / MCP / agent surface.
def _pack_hn_keywords() -> list[str]:
    from frontier_scout.packs import default_packs

    keywords = {"claude code", "skill", "claude", "cursor"}
    for pack in default_packs().values():
        keywords.update(pack.discovery.hn_keywords)
    return sorted(keywords)


HN_KEYWORDS = _pack_hn_keywords()


# ── Item fetchers ───────────────────────────────────────────────────────────


def _make_item(source: str, title: str, url: str, summary: str, date: str) -> dict:
    return {
        "source": source,
        "title": title or "",
        "url": url or "",
        "summary": (summary or "")[:600],
        "date": date,
    }


def fetch_rss(name: str, url: str) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items: list[dict] = []
        for entry in feed.entries[:30]:
            pub = None
            for field_name in ("published_parsed", "updated_parsed"):
                val = getattr(entry, field_name, None)
                if val:
                    pub = datetime.fromtimestamp(time.mktime(val), tz=UTC)
                    break
            if pub and pub >= CUTOFF:
                items.append(
                    _make_item(
                        source=name,
                        title=entry.get("title", ""),
                        url=entry.get("link", ""),
                        summary=entry.get("summary", ""),
                        date=pub.strftime("%Y-%m-%d"),
                    )
                )
        return items
    except Exception as e:
        print(f"  RSS [{name}]: {e}")
        return []


def fetch_github_releases(repo: str, name: str, group: str) -> list[dict]:
    try:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=10"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            # Repo without published releases — fall back to recent commits on the default branch.
            return _fetch_github_commits_fallback(repo, name, group)
        resp.raise_for_status()
        items = []
        for r in resp.json():
            if r.get("draft") or r.get("prerelease"):
                continue
            pub = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
            if pub >= CUTOFF:
                items.append(
                    _make_item(
                        source=f"{group}::{name}",
                        title=f"{name} {r['tag_name']}",
                        url=r["html_url"],
                        summary=r.get("body") or "",
                        date=pub.strftime("%Y-%m-%d"),
                    )
                )
        return items
    except Exception as e:
        print(f"  GitHub [{repo}]: {e}")
        return []


def _fetch_github_commits_fallback(repo: str, name: str, group: str) -> list[dict]:
    """For tree-style repos (anthropics/skills, awesome-mcp-servers) that
    don't publish releases — surface new commits as scout-able items."""
    try:
        url = f"https://api.github.com/repos/{repo}/commits?per_page=10"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        items = []
        for c in resp.json():
            commit = c.get("commit", {})
            pub_str = (commit.get("author") or {}).get("date") or ""
            if not pub_str:
                continue
            pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if pub < CUTOFF:
                continue
            message = (commit.get("message") or "").splitlines()[0][:120]
            items.append(
                _make_item(
                    source=f"{group}::{name}",
                    title=f"{name}: {message}",
                    url=c.get("html_url") or f"https://github.com/{repo}",
                    summary=commit.get("message") or "",
                    date=pub.strftime("%Y-%m-%d"),
                )
            )
        return items[:3]  # tree repos are chatty; cap aggressively
    except Exception as e:
        print(f"  GitHub commits [{repo}]: {e}")
        return []


def fetch_arxiv(category: str) -> list[dict]:
    headers = {"User-Agent": USER_AGENT}
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=cat:{category}"
        "&sortBy=submittedDate&sortOrder=descending&max_results=15"
    )
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code in (429, 503):
            time.sleep(5)
            resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.content)
        items: list[dict] = []
        for entry in root.findall("a:entry", ns):
            pub_str = entry.findtext("a:published", namespaces=ns) or ""
            if not pub_str:
                continue
            pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if pub >= CUTOFF:
                title = (entry.findtext("a:title", namespaces=ns) or "").strip()
                summary = (entry.findtext("a:summary", namespaces=ns) or "").strip()[:500]
                link = next(
                    (
                        el.get("href", "")
                        for el in entry.findall("a:link", ns)
                        if el.get("type") == "text/html"
                    ),
                    "",
                )
                items.append(
                    _make_item(
                        source=f"arXiv {category}",
                        title=title,
                        url=link,
                        summary=summary,
                        date=pub.strftime("%Y-%m-%d"),
                    )
                )
        return items
    except Exception as e:
        print(f"  arXiv [{category}]: {e}")
        return []


def fetch_github_trending(language: str) -> list[dict]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  GitHub Trending: beautifulsoup4 not installed — skipping")
        return []
    try:
        lang_path = "" if language == "all" else f"/{language}"
        url = f"https://github.com/trending{lang_path}?since=weekly"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        today = datetime.now().strftime("%Y-%m-%d")
        for art in soup.select("article.Box-row")[:20]:
            a = art.select_one("h2 a")
            if not a:
                continue
            repo_path = a.get("href", "").strip("/")
            if not repo_path:
                continue
            desc_el = art.select_one("p")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            stars_el = art.select_one("span.d-inline-block.float-sm-right")
            stars_today = (
                stars_el.get_text(strip=True) if stars_el else "0 stars this week"
            )
            items.append(
                _make_item(
                    source=f"Trending: GitHub/{language}",
                    title=repo_path,
                    url=f"https://github.com/{repo_path}",
                    summary=f"[{stars_today}] {desc}".strip(),
                    date=today,
                )
            )
        return items
    except Exception as e:
        print(f"  GitHub Trending [{language}]: {e}")
        return []


def fetch_hf_trending() -> list[dict]:
    try:
        resp = requests.get(
            "https://huggingface.co/api/models",
            params={"sort": "likes7d", "direction": -1, "limit": 20},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        items: list[dict] = []
        today = datetime.now().strftime("%Y-%m-%d")
        for m in resp.json()[:20]:
            model_id = m.get("modelId") or m.get("id", "")
            if not model_id:
                continue
            downloads = m.get("downloads", 0)
            likes = m.get("likes", 0)
            pipeline_tag = m.get("pipeline_tag", "")
            items.append(
                _make_item(
                    source="Trending: HF Models",
                    title=f"{model_id} — {downloads} downloads, {likes} likes",
                    url=f"https://huggingface.co/{model_id}",
                    summary=(
                        f"Trending HuggingFace model. Pipeline: {pipeline_tag}. "
                        f"Tags: {', '.join((m.get('tags') or [])[:8])}"
                    ),
                    date=today,
                )
            )
        return items
    except Exception as e:
        print(f"  HF Trending: {e}")
        return []


def fetch_hn_smart(keywords: list[str]) -> list[dict]:
    since_ts = int(CUTOFF.timestamp())
    seen_ids: set[str] = set()
    items: list[dict] = []
    for kw in keywords:
        try:
            resp = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": kw,
                    "tags": "story",
                    "numericFilters": f"points>40,created_at_i>{since_ts}",
                    "hitsPerPage": 10,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                hid = hit.get("objectID")
                if not hid or hid in seen_ids:
                    continue
                seen_ids.add(hid)
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hid}"
                created_at = hit.get("created_at", "")[:10] or datetime.now().strftime(
                    "%Y-%m-%d"
                )
                raw_title = hit.get("title", "")
                for prefix in ("Show HN: ", "Ask HN: ", "Tell HN: ", "Launch HN: "):
                    if raw_title.startswith(prefix):
                        raw_title = raw_title[len(prefix):]
                        break
                items.append(
                    _make_item(
                        source=f"HN ({kw})",
                        title=raw_title,
                        url=url,
                        summary=f"[{hit.get('points', 0)} pts · {hit.get('num_comments', 0)} comments]",
                        date=created_at,
                    )
                )
        except Exception as e:
            print(f"  HN [{kw}]: {e}")
    return items


# ── Stratified cap ──────────────────────────────────────────────────────────


def _source_group(source_str: str) -> str:
    """Map an item's ``source`` field to one of the SOURCE_QUOTAS keys."""
    s = source_str or ""
    if "::" in s:
        # GitHub watchlist items are tagged "<group>::<name>" by fetch_github_releases.
        return s.split("::", 1)[0]
    if s.startswith("Trending: GitHub"):
        return "github_trending"
    if s.startswith("Trending: HF"):
        return "hf_trending"
    if s.startswith("HN ("):
        return "hn_smart"
    if s.startswith("arXiv "):
        return "arxiv"
    return "rss"


def stratified_cap(
    items: list[dict],
    quotas: dict[str, int] | None = None,
    total_cap: int = MAX_ITEMS,
) -> list[dict]:
    """Apply per-source-group quotas, then redistribute unused capacity.

    Two-pass deterministic algorithm:
      1. Each group takes up to its base quota (sorted newest-first within group).
      2. If the total is below ``total_cap`` and some groups have leftovers,
         redistribute round-robin (sorted group names for determinism).
    """
    quotas = quotas or SOURCE_QUOTAS
    by_group: dict[str, list[dict]] = {}
    for item in items:
        by_group.setdefault(_source_group(item.get("source", "")), []).append(item)

    for group_items in by_group.values():
        group_items.sort(key=lambda x: x.get("date", ""), reverse=True)

    taken: dict[str, list[dict]] = {}
    leftovers: dict[str, list[dict]] = {}
    for group, group_items in by_group.items():
        limit = quotas.get(group, 0)
        taken[group] = group_items[:limit]
        leftovers[group] = group_items[limit:]

    out_count = sum(len(v) for v in taken.values())
    remaining = max(0, total_cap - out_count)

    if remaining > 0:
        round_robin_groups = sorted(g for g, lo in leftovers.items() if lo)
        while remaining > 0 and round_robin_groups:
            progress = False
            for group in list(round_robin_groups):
                if remaining <= 0:
                    break
                if not leftovers[group]:
                    round_robin_groups.remove(group)
                    continue
                taken[group].append(leftovers[group].pop(0))
                remaining -= 1
                progress = True
            if not progress:
                break

    out: list[dict] = []
    for group in sorted(taken.keys()):
        out.extend(taken[group])
    return out


# ── Dedupe + seen-tool filter ───────────────────────────────────────────────


def _content_hash(item: dict) -> str:
    title = (item.get("title") or "").lower().strip()
    url = item.get("url", "")
    try:
        parsed = urlparse(url)
        canonical = f"{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        canonical = url
    raw = f"{title}|{canonical}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def dedupe(items: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        h = _content_hash(item)
        if h in seen:
            continue
        seen.add(h)
        out.append(item)
    return out, len(items) - len(out)


# Type signature for the seen-tools predicate. The CLI passes in a SQLite-
# backed implementation from fs_cli.db.seen_check_factory(); test code can
# pass a simpler dict-backed lambda.
SeenCheck = Callable[[str], bool]


def filter_by_seen(
    items: list[dict], seen_check: SeenCheck | None
) -> tuple[list[dict], int]:
    """Drop items whose URL is in the user's ``seen_tools`` table."""
    if seen_check is None:
        return items, 0
    kept: list[dict] = []
    dropped = 0
    for item in items:
        url = item.get("url", "")
        if url and seen_check(url):
            dropped += 1
        else:
            kept.append(item)
    return kept, dropped


# ── LLM passes ──────────────────────────────────────────────────────────────


_PROVIDER = None


def _provider():
    """Resolve (once) the active LLM backend for this scan."""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = resolve_provider()
    return _PROVIDER


def score_items(
    items: list[dict], stack_profile: dict | None = None
) -> tuple[list[dict], float]:
    if not items:
        return [], 0.0

    if len(items) > MAX_ITEMS:
        before = len(items)
        items = stratified_cap(items)
        print(f"  Stratified cap: {before} → {len(items)} items")

    batch = "\n\n".join(
        f"<source_data idx={i}>\n"
        f"  source: {item['source']}\n"
        f"  title: {item['title']}\n"
        f"  summary: {item['summary'][:300]}\n"
        f"</source_data>"
        for i, item in enumerate(items)
    )

    provider = _provider()
    model_id = provider.model(FAST)
    resp = call_with_retry(
        provider,
        "scout-score",
        model=model_id,
        max_tokens=16000,
        system=cached_system_blocks(stack_profile),
        tools=[SCORE_ITEMS_TOOL],
        tool_choice={"type": "tool", "name": "score_items"},
        messages=[{"role": "user", "content": f"Score these {len(items)} items.\n\n{batch}"}],
    )
    cost = log_call("scout-score", model_id, resp.usage)
    print(
        f"  Score pass: {resp.usage.input_tokens} in + {resp.usage.output_tokens} out "
        f"(cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)}) = ${cost:.4f}"
    )
    if resp.usage.output_tokens >= 16000:
        print("  ⚠️  Score pass hit max_tokens=16000 — output may be truncated.")

    tool_use = next(
        (b for b in resp.content if getattr(b, "type", None) == "tool_use"), None
    )
    if tool_use is None:
        print("  ⚠️  Score pass returned no tool payload; defaulting all scores to 0.")
        for item in items:
            item.setdefault("score", 0)
            item.setdefault("category", "dev_tool")
            item.setdefault("tags", [])
        return items, cost

    for entry in tool_use.input.get("scores", []) or []:
        i = entry["index"]
        if 0 <= i < len(items):
            items[i]["score"] = entry["score"]
            items[i]["category"] = entry["category"]
            items[i]["tags"] = [
                t.lower()
                for t in (entry.get("tags") or [])
                if isinstance(t, str) and t
            ]

    for item in items:
        item.setdefault("score", 0)
        item.setdefault("category", "dev_tool")
        item.setdefault("tags", [])

    return sorted(items, key=lambda x: x["score"], reverse=True), cost


def _attach_tags(verdicts: list[dict], scored_items: list[dict]) -> list[dict]:
    if not verdicts:
        return verdicts
    by_url = {(item.get("url") or ""): item for item in scored_items if item.get("url")}
    for v in verdicts:
        if v.get("tags"):
            continue
        url = v.get("source_url") or ""
        match = by_url.get(url)
        if match is None:
            tool_lc = (v.get("tool_name") or "").lower().strip()
            if tool_lc:
                for item in scored_items:
                    title_lc = (item.get("title") or "").lower()
                    if tool_lc and tool_lc in title_lc:
                        match = item
                        break
        v["tags"] = list((match or {}).get("tags") or [])
    return verdicts


def generate_verdicts(
    top: list[dict], stack_profile: dict | None = None
) -> tuple[list[dict], float]:
    if not top:
        return [], 0.0
    items_text = "\n\n".join(
        f"<source_data idx={i}>\n"
        f"  source: {item['source']}\n"
        f"  title: {item['title']}\n"
        f"  url: {item['url']}\n"
        f"  category: {item.get('category', 'dev_tool')}\n"
        f"  date: {item['date']}\n"
        f"  summary: {item['summary']}\n"
        f"</source_data>"
        for i, item in enumerate(top)
    )
    today = datetime.now().strftime("%Y-%m-%d")

    provider = _provider()
    model_id = provider.model(FAST)
    resp = call_with_retry(
        provider,
        "scout-verdict",
        model=model_id,
        max_tokens=4000,
        system=cached_system_blocks(stack_profile),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "emit_verdicts"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Today is {today}. Emit verdicts for these {len(top)} items. "
                    "Lead with the highest-value. Skip anything that doesn't deserve "
                    "a verdict.\n\n"
                    f"{items_text}"
                ),
            }
        ],
    )
    cost = log_call("scout-verdict", model_id, resp.usage)
    print(
        f"  Verdict pass: {resp.usage.input_tokens} in + {resp.usage.output_tokens} out "
        f"(cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)}) = ${cost:.4f}"
    )
    tool_use = next(
        (b for b in resp.content if getattr(b, "type", None) == "tool_use"), None
    )
    if tool_use is None:
        print("  ⚠️  Verdict pass returned no tool payload.")
        return [], cost
    return tool_use.input.get("verdicts", []) or [], cost


# ── Public entry point ──────────────────────────────────────────────────────


@dataclass
class ScanResult:
    """Returned by :func:`run_scan` — everything the caller needs to persist
    the run to SQLite and report it."""

    scanned: int
    candidates: int
    dedup_drops: int
    seen_drops: int
    verdicts: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_s: float = 0.0
    judge_summary: str = ""
    judge_rating: str = "medium"
    judge_used_fallback: bool = False


def _judge_enabled() -> bool:
    return os.environ.get("JUDGE_ENABLED", "true").strip().lower() not in {
        "false",
        "0",
        "no",
    }


def fetch_all() -> list[dict]:
    """Run every fetcher in parallel and return the flat item list.

    arXiv is serialized because their API rate-limits anonymous traffic.
    """
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = (
            [ex.submit(fetch_rss, name, url) for name, url in RSS_FEEDS]
            + [
                ex.submit(fetch_github_releases, repo, name, group)
                for repo, name, group in GITHUB_WATCHLIST
            ]
            + [ex.submit(fetch_github_trending, lang) for lang in TRENDING_LANGS]
            + [ex.submit(fetch_hf_trending)]
            + [ex.submit(fetch_hn_smart, HN_KEYWORDS)]
        )
        all_items: list[dict] = [item for f in futures for item in f.result()]

    for i, cat in enumerate(ARXIV_CATS):
        if i > 0:
            time.sleep(3)
        all_items.extend(fetch_arxiv(cat))

    return all_items


def run_scan(
    *,
    stack_profile: dict | None = None,
    seen_check: SeenCheck | None = None,
    output_writer: Callable[[ScanResult], None] | None = None,
    dry_run: bool = False,
) -> ScanResult:
    """Run one scout pass and return a :class:`ScanResult`.

    Args:
        stack_profile: parsed ``stack.yaml`` (see prompts.render_stack_profile).
        seen_check: predicate the funnel calls per-URL; when truthy the item
            is filtered out. Typically backed by SQLite ``seen_tools``.
        output_writer: optional callback invoked with the final result, e.g.
            to persist verdicts to the SQLite store.
        dry_run: when True (or DRY_RUN=1), no LLM calls are made and a
            single placeholder verdict is returned. Useful for plumbing tests.
    """
    start = time.time()
    dry_run = dry_run or os.environ.get("DRY_RUN") == "1"

    print(f"🔍 Frontier Scout — scanning since {CUTOFF.strftime('%Y-%m-%d')}")
    if dry_run:
        print("  DRY_RUN=1 — using fixture scan, no LLM calls.")

    if dry_run:
        from demo import SAMPLE_VERDICTS

        result = ScanResult(
            scanned=len(SAMPLE_VERDICTS) * 50,
            candidates=len(SAMPLE_VERDICTS) * 8,
            dedup_drops=0,
            seen_drops=0,
            verdicts=list(SAMPLE_VERDICTS),
            cost_usd=0.0,
            duration_s=round(time.time() - start, 2),
            judge_summary="Dry-run scan — verdicts pulled from scripts/demo.py.",
            judge_rating="medium",
        )
        if output_writer:
            output_writer(result)
        return result

    all_items = fetch_all()
    scanned = len(all_items)
    print(f"📥 {scanned} items from past 7 days across all sources")

    if scanned == 0:
        result = ScanResult(
            scanned=0,
            candidates=0,
            dedup_drops=0,
            seen_drops=0,
            verdicts=[],
            cost_usd=0.0,
            duration_s=round(time.time() - start, 2),
        )
        if output_writer:
            output_writer(result)
        quality_logger.log_run("scout", items_scanned=0, total_cost_usd=0.0)
        return result

    all_items, dedup_drops = dedupe(all_items)
    print(f"🧹 Dedupe: dropped {dedup_drops} duplicates → {len(all_items)} unique")

    all_items, seen_drops = filter_by_seen(all_items, seen_check)
    if seen_check:
        print(f"👀 Seen-tool filter: dropped {seen_drops} already-known → {len(all_items)} fresh")

    candidates = len(all_items)
    if candidates == 0:
        result = ScanResult(
            scanned=scanned,
            candidates=0,
            dedup_drops=dedup_drops,
            seen_drops=seen_drops,
            verdicts=[],
            cost_usd=0.0,
            duration_s=round(time.time() - start, 2),
        )
        if output_writer:
            output_writer(result)
        quality_logger.log_run(
            "scout",
            items_scanned=scanned,
            dedup_drops=dedup_drops,
            seen_drops=seen_drops,
            candidates=0,
        )
        return result

    scored, score_cost = score_items(all_items, stack_profile)
    top = [it for it in scored if it.get("score", 0) >= 6][:12]
    if not top:
        print("  No items scored ≥ 6; falling back to top 4.")
        top = scored[:4]

    draft_verdicts, verdict_cost = generate_verdicts(top, stack_profile)

    judge_cost = 0.0
    judge_result: dict[str, Any] = {
        "decisions": [],
        "missed": [],
        "quality_self_rating": "medium",
        "judge_summary": "",
    }
    final_verdicts: list[dict] = list(draft_verdicts)

    if _judge_enabled() and draft_verdicts:
        print("⚖️  Judge pass (Opus)...")
        judge_result, judge_cost = judge_mod.critique(draft_verdicts, scored, stack_profile)
        final_verdicts = judge_mod.apply_judge_decisions(
            draft_verdicts, scored, judge_result
        )
    else:
        if not _judge_enabled():
            print("  JUDGE_ENABLED=false — skipping Opus pass.")

    final_verdicts = _attach_tags(final_verdicts, scored)

    print("🛡  Policy gates...")
    final_verdicts, dropped_by_policy = validate_verdicts(
        final_verdicts, source_items=scored
    )
    for d in dropped_by_policy:
        tn = (d.get("verdict") or {}).get("tool_name", "?")
        print(f"  ❌ dropped {tn!r}: {d['reason']}")
    print(
        f"  Policy: {len(final_verdicts)} kept, {len(dropped_by_policy)} dropped"
    )

    total_cost = score_cost + verdict_cost + judge_cost
    duration = round(time.time() - start, 2)

    result = ScanResult(
        scanned=scanned,
        candidates=candidates,
        dedup_drops=dedup_drops,
        seen_drops=seen_drops,
        verdicts=final_verdicts,
        cost_usd=round(total_cost, 6),
        duration_s=duration,
        judge_summary=judge_result.get("judge_summary", ""),
        judge_rating=judge_result.get("quality_self_rating", "medium"),
        judge_used_fallback=bool(judge_result.get("_judge_used_fallback")),
    )

    if output_writer:
        output_writer(result)

    quality_logger.log_run(
        "scout",
        items_scanned=scanned,
        dedup_drops=dedup_drops,
        seen_drops=seen_drops,
        candidates=candidates,
        verdicts_pre_judge=len(draft_verdicts),
        verdicts_post_judge=len(final_verdicts),
        policy_dropped=len(dropped_by_policy),
        judge_self_rating=result.judge_rating,
        total_cost_usd=result.cost_usd,
        duration_s=duration,
        judge_used_fallback=result.judge_used_fallback,
        llm_retries_total=LLM_STATS.total_retries,
        llm_retries_by_component=dict(LLM_STATS.by_component),
    )
    print(
        f"\n✅ Done. Cost ${total_cost:.4f} · {duration}s · "
        f"verdicts {len(final_verdicts)} · LLM retries: {LLM_STATS.total_retries}"
    )
    return result


def main() -> int:
    """Standalone entry point.

    The CLI (`frontier-scout scan`) is the supported caller; this exists so
    the module can be executed directly for debugging.
    """
    try:
        result = run_scan()
    except BaseException as exc:  # noqa: BLE001
        import sys
        import traceback

        print(f"\n💥 Scout CRASHED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        quality_logger.log_run(
            "scout",
            crashed=True,
            error_type=type(exc).__name__,
            error_msg=str(exc)[:500],
            llm_retries_total=LLM_STATS.total_retries,
            llm_retries_by_component=dict(LLM_STATS.by_component),
        )
        raise
    return 0 if result.verdicts or result.scanned == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
