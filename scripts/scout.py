#!/usr/bin/env python3
"""
AI Telemetry — Weekly Scout (v3).

Runs every Monday 09:00 IST. Surfaces high-signal AI/ML developments from the
past 7 days across ~47 source streams (first-party labs + curated newsletters +
practitioner blogs + adoption-velocity signals + arXiv).

Pipeline:
  fetch (parallel)
    → dedupe by content hash
    → Mem0 prior-verdict filter (skip tools we covered in last 30 days)
    → Sonnet 4.6 score pass (0-10 + category)
    → Sonnet 4.6 verdict pass (structured tool use)
    → Opus 4.7 RLAIF judge pass (extended thinking)
    → write briefing markdown
    → Mem0 seed (post-verdict)
    → quality log
    → Slack post

Env:
  ANTHROPIC_API_KEY    required
  GITHUB_TOKEN         optional (raises GitHub API rate limit 60→5000/hr)
  OPENAI_API_KEY       optional (enables Mem0 prior-filter and post-seed)
  SLACK_WEBHOOK_URL    or SLACK_BOT_TOKEN — for Slack post
  DRY_RUN=1            print Slack payload instead of sending
"""

import hashlib
import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import anthropic
import feedparser
import requests

from cost_tracker import log_call
from prompts import cached_system_blocks
from tools import SCORE_ITEMS_TOOL, VERDICT_TOOL
import judge as judge_mod
import quality_logger
import slack_post
from llm_client import STATS as LLM_STATS, call_with_retry
from validators import validate_verdicts

# ── Config ────────────────────────────────────────────────────────────────────

CLIENT: anthropic.Anthropic | None = None
MODEL = "claude-sonnet-4-6"
CUTOFF = datetime.now(timezone.utc) - timedelta(days=7)

REPO_ROOT = Path(__file__).parent.parent
BRIEFINGS = REPO_ROOT / "briefings"
ARCHIVE = REPO_ROOT / "archive" / "signals"
WEEKLY_OUT = REPO_ROOT / "WEEKLY_SIGNAL.md"

# Hard cap to bound worst-case scoring cost (Sonnet ~$0.20 at this cap).
MAX_ITEMS = 250

# Per-source-group quotas for stratified capping. Sums to MAX_ITEMS; ordered
# by signal density (curated newsletters and watchlist releases first).
SOURCE_QUOTAS = {
    "rss":             90,   # 19 RSS feeds × ~5 items each, capped here
    "github_release":  40,   # 20 named repos, usually 1-3 per repo
    "github_trending": 30,   # 2 trending langs × 15 each
    "hf_trending":     20,
    "hn_smart":        25,
    "producthunt":     15,
    "paperswithcode":  10,
    "arxiv":           20,   # 3 categories × ~7 each
}
assert sum(SOURCE_QUOTAS.values()) <= MAX_ITEMS, "quotas exceed MAX_ITEMS"

USER_AGENT = "ai-telemetry/2.0 (+https://github.com/YOUR_ORG/ai-telemetry)"


def _client() -> anthropic.Anthropic:
    """Create the Anthropic client only when a live pipeline call is made."""
    global CLIENT
    if CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for Scout model calls")
        CLIENT = anthropic.Anthropic(api_key=api_key)
    return CLIENT


# ── Sources ───────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    # First-party labs
    ("Anthropic News",     "https://www.anthropic.com/news/rss.xml"),
    ("OpenAI Blog",        "https://openai.com/blog/rss.xml"),
    ("Google DeepMind",    "https://deepmind.google/blog/rss.xml"),
    ("Mistral News",       "https://mistral.ai/news/feed.xml"),
    ("Hugging Face Blog",  "https://huggingface.co/blog/feed.xml"),
    # Curated AI newsletters (the "TLDR layer")
    ("TLDR AI",            "https://tldr.tech/api/rss/ai"),
    ("AINews (Smol AI)",   "https://buttondown.com/ainews/rss"),
    ("Ben's Bites",        "https://www.bensbites.co/feed"),
    ("The Batch",          "https://www.deeplearning.ai/the-batch/feed/"),
    ("Import AI",          "https://jack-clark.net/feed/"),
    ("Latent Space",       "https://www.latent.space/feed"),
    # Practitioner blogs (substack proxies for LinkedIn AI voices)
    ("Simon Willison",     "https://simonwillison.net/atom/everything/"),
    ("Eugene Yan",         "https://eugeneyan.com/rss/"),
    ("Ahead of AI",        "https://sebastianraschka.com/rss_feed.xml"),
    ("AI Tidbits",         "https://www.aitidbits.ai/feed"),
    ("Cameron Wolfe",      "https://cameronrwolfe.substack.com/feed"),
    ("HuggingFace Papers", "https://huggingface.co/papers/rss"),
    # Community top-of-stack
    ("r/MachineLearning",  "https://www.reddit.com/r/MachineLearning/top.rss?t=week"),
    ("r/LocalLLaMA",       "https://www.reddit.com/r/LocalLLaMA/top.rss?t=week"),
]

GITHUB_REPOS = [
    # Existing watchlist (frameworks the configured team uses or evaluates)
    ("langchain-ai/langchain",             "LangChain"),
    ("langchain-ai/langgraph",             "LangGraph"),
    ("anthropics/claude-plugins-official", "Claude Code Plugins"),
    ("mem0ai/mem0",                        "mem0"),
    ("openai/openai-python",               "OpenAI Python SDK"),
    ("BerriAI/litellm",                    "LiteLLM"),
    ("run-llama/llama_index",              "LlamaIndex"),
    ("pydantic/pydantic-ai",               "PydanticAI"),
    ("agentskills/agentskills",            "agentskills.io"),
    # Infra & inference
    ("vllm-project/vllm",                  "vLLM"),
    ("ollama/ollama",                      "Ollama"),
    ("modal-labs/modal-client",            "Modal"),
    # Frameworks gaining traction
    ("anthropics/anthropic-sdk-python",    "Anthropic SDK"),
    ("microsoft/autogen",                  "AutoGen"),
    ("huggingface/transformers",           "Transformers"),
    ("e2b-dev/E2B",                        "E2B Sandbox"),
    ("openai/openai-agents-python",        "OpenAI Agents SDK"),
    ("getzep/graphiti",                    "Graphiti"),
    ("block/goose",                        "Goose"),
]

ARXIV_CATS = ["cs.AI", "cs.CL", "cs.LG"]

# Smart HN keyword filter
HN_KEYWORDS = [
    "llm", "claude", "gpt", "anthropic", "openai", "agents",
    "langchain", "rag", "vector database", "embeddings",
]

# GitHub Trending periods
TRENDING_LANGS = ["python", "all"]


# ── Fetchers ──────────────────────────────────────────────────────────────────

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
        items = []
        for entry in feed.entries[:30]:
            pub = None
            for field in ["published_parsed", "updated_parsed"]:
                val = getattr(entry, field, None)
                if val:
                    pub = datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
                    break
            if pub and pub >= CUTOFF:
                items.append(_make_item(
                    source=name,
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    summary=entry.get("summary", ""),
                    date=pub.strftime("%Y-%m-%d"),
                ))
        return items
    except Exception as e:
        print(f"  RSS [{name}]: {e}")
        return []


def fetch_github_releases(repo: str, name: str) -> list[dict]:
    try:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=10"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        items = []
        for r in resp.json():
            if r.get("draft") or r.get("prerelease"):
                continue
            pub = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
            if pub >= CUTOFF:
                items.append(_make_item(
                    source=f"Release: {name}",
                    title=f"{name} {r['tag_name']}",
                    url=r["html_url"],
                    summary=r.get("body") or "",
                    date=pub.strftime("%Y-%m-%d"),
                ))
        return items
    except Exception as e:
        print(f"  GitHub [{repo}]: {e}")
        return []


def fetch_arxiv(category: str) -> list[dict]:
    # arXiv API requires a descriptive User-Agent and rate-limits anonymous traffic.
    # https://info.arxiv.org/help/api/user-manual.html
    headers = {"User-Agent": USER_AGENT}
    url = (
        f"https://export.arxiv.org/api/query"
        f"?search_query=cat:{category}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results=30"
    )
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code in (429, 503):
            time.sleep(5)
            resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.content)
        items = []
        for entry in root.findall("a:entry", ns):
            pub_str = entry.findtext("a:published", namespaces=ns) or ""
            if not pub_str:
                continue
            pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if pub >= CUTOFF:
                title = (entry.findtext("a:title", namespaces=ns) or "").strip()
                summary = (entry.findtext("a:summary", namespaces=ns) or "").strip()[:500]
                link = next(
                    (el.get("href", "") for el in entry.findall("a:link", ns)
                     if el.get("type") == "text/html"),
                    "",
                )
                items.append(_make_item(
                    source=f"arXiv {category}",
                    title=title,
                    url=link,
                    summary=summary,
                    date=pub.strftime("%Y-%m-%d"),
                ))
        return items
    except Exception as e:
        print(f"  arXiv [{category}]: {e}")
        return []


def fetch_github_trending(language: str) -> list[dict]:
    """Scrape GitHub Trending HTML — no official API but stable selectors."""
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
        items = []
        today = datetime.now().strftime("%Y-%m-%d")
        for art in soup.select("article.Box-row")[:25]:
            a = art.select_one("h2 a")
            if not a:
                continue
            repo_path = a.get("href", "").strip("/")
            if not repo_path:
                continue
            desc_el = art.select_one("p")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            stars_el = art.select_one("span.d-inline-block.float-sm-right")
            stars_today = stars_el.get_text(strip=True) if stars_el else "0 stars this week"
            # Keep title clean (just owner/repo); put velocity in summary so the
            # LLM sees adoption-signal context without polluting tool_name.
            items.append(_make_item(
                source=f"Trending: GitHub/{language}",
                title=repo_path,
                url=f"https://github.com/{repo_path}",
                summary=f"[{stars_today}] {desc}".strip(),
                date=today,
            ))
        return items
    except Exception as e:
        print(f"  GitHub Trending [{language}]: {e}")
        return []


def fetch_hf_trending() -> list[dict]:
    """Top trending models on HuggingFace — proven adoption signal.
    HF's `sort=trending` was deprecated; we use `sort=likes7d` (likes in last 7d)
    as the closest proxy for "what real practitioners are adopting this week".
    """
    try:
        resp = requests.get(
            "https://huggingface.co/api/models",
            params={"sort": "likes7d", "direction": -1, "limit": 25},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        items = []
        today = datetime.now().strftime("%Y-%m-%d")
        for m in resp.json()[:25]:
            model_id = m.get("modelId") or m.get("id", "")
            if not model_id:
                continue
            downloads = m.get("downloads", 0)
            likes = m.get("likes", 0)
            pipeline_tag = m.get("pipeline_tag", "")
            items.append(_make_item(
                source="Trending: HF Models",
                title=f"{model_id} — {downloads} downloads, {likes} likes",
                url=f"https://huggingface.co/{model_id}",
                summary=f"Trending HuggingFace model. Pipeline: {pipeline_tag}. "
                        f"Tags: {', '.join((m.get('tags') or [])[:8])}",
                date=today,
            ))
        return items
    except Exception as e:
        print(f"  HF Trending: {e}")
        return []


def fetch_producthunt_ai() -> list[dict]:
    """AI category from ProductHunt RSS — product discovery layer."""
    return fetch_rss("ProductHunt AI", "https://www.producthunt.com/feed?category=artificial-intelligence")


def fetch_hn_smart(keywords: list[str]) -> list[dict]:
    """Algolia HN search filtered by keywords + min upvotes + past week."""
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
                    "numericFilters": f"points>50,created_at_i>{since_ts}",
                    "hitsPerPage": 15,
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
                created_at = hit.get("created_at", "")[:10] or datetime.now().strftime("%Y-%m-%d")
                # Strip HN forum prefixes that would otherwise leak into tool_name.
                raw_title = hit.get("title", "")
                for prefix in ("Show HN: ", "Ask HN: ", "Tell HN: ", "Launch HN: "):
                    if raw_title.startswith(prefix):
                        raw_title = raw_title[len(prefix):]
                        break
                items.append(_make_item(
                    source=f"HN ({kw})",
                    title=raw_title,
                    url=url,
                    summary=f"[{hit.get('points', 0)} points · {hit.get('num_comments', 0)} comments]",
                    date=created_at,
                ))
        except Exception as e:
            print(f"  HN [{kw}]: {e}")
    return items


def fetch_paperswithcode_trending() -> list[dict]:
    """Trending papers with code (the 'actually usable' signal)."""
    return fetch_rss("PapersWithCode", "https://paperswithcode.com/feed.xml")


# ── Stratified source-group cap ───────────────────────────────────────────────

def _source_group(source_str: str) -> str:
    """Map an item's `source` field to a quota group key.

    Source strings produced by fetchers:
      - RSS feeds: "<feed name>" (anything not matching below)
      - GitHub releases: "Release: <name>"
      - GitHub trending: "Trending: GitHub/<lang>"
      - HF trending: "Trending: HF Models"
      - HN smart: "HN (<keyword>)"
      - ProductHunt: "ProductHunt AI"
      - PapersWithCode: "PapersWithCode"
      - arXiv: "arXiv <cat>"
    """
    s = source_str or ""
    if s.startswith("Release: "):
        return "github_release"
    if s.startswith("Trending: GitHub"):
        return "github_trending"
    if s.startswith("Trending: HF"):
        return "hf_trending"
    if s.startswith("HN ("):
        return "hn_smart"
    if s == "ProductHunt AI":
        return "producthunt"
    if s == "PapersWithCode":
        return "paperswithcode"
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
      2. If the total is below total_cap and some groups have leftover items,
         redistribute the unused capacity across those groups round-robin.

    Recall is preserved for late-completing source groups (arXiv,
    paperswithcode) that the v2 list slice silently dropped. The redistribution
    pass means we don't leave Sonnet input-token slots on the floor when one
    group runs short on a given week.
    """
    quotas = quotas or SOURCE_QUOTAS
    by_group: dict[str, list[dict]] = {}
    for item in items:
        by_group.setdefault(_source_group(item.get("source", "")), []).append(item)

    # Sort within each group: newer first; date is YYYY-MM-DD so string sort works.
    for group_items in by_group.values():
        group_items.sort(key=lambda x: x.get("date", ""), reverse=True)

    # Pass 1: take up to base quota from each group; track leftovers.
    taken: dict[str, list[dict]] = {}
    leftovers: dict[str, list[dict]] = {}
    for group, group_items in by_group.items():
        limit = quotas.get(group, 0)
        taken[group] = group_items[:limit]
        leftovers[group] = group_items[limit:]

    out_count = sum(len(v) for v in taken.values())
    remaining = max(0, total_cap - out_count)

    # Pass 2: round-robin distribute remaining capacity across groups with
    # leftovers, by group name (deterministic ordering).
    if remaining > 0:
        round_robin_groups = sorted(g for g, l in leftovers.items() if l)
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

    # Concatenate in a stable group order
    out: list[dict] = []
    for group in sorted(taken.keys()):
        out.extend(taken[group])
    return out


# ── Dedup + Mem0 prior-filter ─────────────────────────────────────────────────

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


def filter_by_mem0(items: list[dict]) -> tuple[list[dict], int]:
    """Drop items where Mem0 has a verdict ≤30 days old. Best-effort."""
    try:
        from memory import is_available, mem
    except Exception:
        return items, 0
    if not is_available():
        return items, 0
    kept = []
    dropped = 0
    for item in items:
        try:
            prior = mem.prior_verdict(item.get("title", ""), days=30, threshold=0.78)
        except Exception:
            prior = None
        if prior is None:
            kept.append(item)
        else:
            dropped += 1
    return kept, dropped


# ── Intelligence Pipeline ─────────────────────────────────────────────────────

def score_items(items: list[dict]) -> tuple[list[dict], float]:
    """Sonnet pass 1: score 0-10 relevance, tag category. Forced via tool use."""
    if not items:
        return [], 0.0

    # Stratified per-source-group cap (Round 3 fix: was a dumb list slice that
    # silently dropped late-completing source groups).
    if len(items) > MAX_ITEMS:
        before = len(items)
        items = stratified_cap(items)
        print(f"⚠️  {before} items — stratified cap to {len(items)} across source groups")

    # Wrap items in <source_data> tags so the system prompt's
    # prompt-injection clause has a target it can refer to. The model is
    # instructed (in cached_system_blocks) never to follow instructions
    # inside these tags.
    batch = "\n\n".join(
        f"<source_data idx={i}>\n"
        f"  source: {item['source']}\n"
        f"  title: {item['title']}\n"
        f"  summary: {item['summary'][:300]}\n"
        f"</source_data>"
        for i, item in enumerate(items)
    )

    resp = call_with_retry(
        _client(),
        "scout-score",
        model=MODEL,
        max_tokens=8000,
        system=cached_system_blocks(),
        tools=[SCORE_ITEMS_TOOL],
        tool_choice={"type": "tool", "name": "score_items"},
        messages=[{
            "role": "user",
            "content": f"Score these {len(items)} items.\n\n{batch}",
        }],
    )
    cost = log_call("scout-score", MODEL, resp.usage)
    print(f"  Score pass: {resp.usage.input_tokens} in + {resp.usage.output_tokens} out "
          f"(cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)}) = ${cost:.4f}")

    tool_use = next(b for b in resp.content if b.type == "tool_use")
    for entry in tool_use.input.get("scores", []) or []:
        i = entry["index"]
        if 0 <= i < len(items):
            items[i]["score"] = entry["score"]
            items[i]["category"] = entry["category"]

    for item in items:
        item.setdefault("score", 0)
        item.setdefault("category", "tool")

    return sorted(items, key=lambda x: x["score"], reverse=True), cost


def generate_verdicts(top: list[dict]) -> tuple[list[dict], float]:
    """Sonnet pass 2: emit structured verdicts via tool use."""
    if not top:
        return [], 0.0
    items_text = "\n\n".join(
        f"<source_data idx={i}>\n"
        f"  source: {item['source']}\n"
        f"  title: {item['title']}\n"
        f"  url: {item['url']}\n"
        f"  category: {item.get('category', 'tool')}\n"
        f"  date: {item['date']}\n"
        f"  summary: {item['summary']}\n"
        f"</source_data>"
        for i, item in enumerate(top)
    )
    today = datetime.now().strftime("%Y-%m-%d")

    resp = call_with_retry(
        _client(),
        "scout-verdict",
        model=MODEL,
        max_tokens=4000,
        system=cached_system_blocks(),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "emit_verdicts"},
        messages=[{
            "role": "user",
            "content": (
                f"Today is {today}. Emit verdicts for these {len(top)} items. "
                f"Lead with the highest-value. Skip anything that doesn't deserve a verdict.\n\n"
                f"{items_text}"
            ),
        }],
    )
    cost = log_call("scout-verdict", MODEL, resp.usage)
    print(f"  Verdict pass: {resp.usage.input_tokens} in + {resp.usage.output_tokens} out "
          f"(cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)}) = ${cost:.4f}")

    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return tool_use.input["verdicts"], cost


# ── Output ────────────────────────────────────────────────────────────────────

VERDICT_LABEL = {"adopt": "🟢 ADOPT", "trial": "🟡 TRIAL", "assess": "⚪ ASSESS", "hold": "🔴 HOLD"}
SOC2_LABEL = {"safe": "✅ SOC2-safe", "conditional": "⚠️ SOC2-conditional", "blocked": "❌ SOC2-blocked"}
CAT_LABEL = {
    "frontier_model": "🧠 Frontier Models",
    "orchestration":  "🤖 Orchestration & Agents",
    "tool":           "🛠️ Tools & Frameworks",
    "data":           "📊 Data Ecosystem",
    "compute":        "⚡ Compute & Hardware",
    "security":       "🔐 Security & Compliance",
}
SEV_LABEL = {"critical": "🔥", "high": "⭐", "standard": "📌"}


def write_briefing(verdicts: list[dict], scanned: int, candidates: int, total_cost: float, judge_meta: dict) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    n_sources = (
        len(RSS_FEEDS) + len(GITHUB_REPOS) + len(ARXIV_CATS) + len(TRENDING_LANGS) + 4
    )
    lines = [
        f"# AI Telemetry — Weekly Briefing · {today}",
        f"> Scanned **{scanned}** items across **{n_sources}** sources. "
        f"**{candidates}** unique candidates after dedup + Mem0 prior-filter. "
        f"**{len(verdicts)}** verdicts after RLAIF judge pass. "
        f"Run cost **${total_cost:.4f}** (cached). "
        f"Judge confidence: **{judge_meta.get('quality_self_rating', 'medium')}**.",
        "",
        f"> _{judge_meta.get('judge_summary', '')}_",
        "",
    ]
    for v in verdicts:
        sev = SEV_LABEL.get(v.get("severity", "standard"), "📌")
        readiness = v.get("readiness", 3)
        meter = "▰" * readiness + "▱" * (5 - readiness)
        lines += [
            f"### {sev} [{v['tool_name']}]({v['source_url']}) — {VERDICT_LABEL[v['verdict']]} "
            f"— {today} — {CAT_LABEL[v['category']]} — {SOC2_LABEL[v['soc2']]}",
            f"**What**: {v['what']}",
            f"**Why it matters**: {v['why_it_matters']}",
            f"**Adoption cost**: {v['adoption_cost']}",
            f"**Next action**: {v['next_action']}",
            f"**Readiness**: `{meter}` {readiness}/5",
            "",
        ]
    lines += [
        "---",
        "*Dig deeper: `evaluate <tool>` · Build skill: `lab <tool>` · Recall past verdicts: `recall <topic>`*",
    ]
    content = "\n".join(lines)

    BRIEFINGS.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    out_briefing = BRIEFINGS / f"{today}.md"
    out_briefing.write_text(content)
    (ARCHIVE / f"{today}.md").write_text(content)
    WEEKLY_OUT.write_text(content)
    return out_briefing


def seed_mem0(verdicts: list[dict]) -> None:
    """Best-effort write to Mem0. Silently skip if not configured."""
    try:
        from memory import is_available, mem
    except Exception as e:
        print(f"  Mem0 import failed: {e}")
        return
    if not is_available():
        print("  Mem0: not configured (OPENAI_API_KEY missing or mem0ai not installed) — skipping")
        return
    for v in verdicts:
        try:
            text = (
                f"{v['tool_name']} — {v['verdict'].upper()} — {v['category']} — SOC2 {v['soc2']}\n"
                f"What: {v['what']}\nWhy: {v['why_it_matters']}\n"
                f"Cost: {v['adoption_cost']}\nNext: {v['next_action']}"
            )
            mem.add_verdict(
                tool=v["tool_name"],
                verdict=v["verdict"],
                soc2=v["soc2"],
                category=v["category"],
                text=text,
            )
        except Exception as e:
            print(f"  Mem0 write failed for {v.get('tool_name', '?')}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def _main_impl():
    start = time.time()
    print(f"🔍 Scout v3 — scanning since {CUTOFF.strftime('%Y-%m-%d')}\n")

    # Fetch in parallel; arXiv sequentially (rate limit)
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = (
            [ex.submit(fetch_rss, name, url) for name, url in RSS_FEEDS]
            + [ex.submit(fetch_github_releases, repo, name) for repo, name in GITHUB_REPOS]
            + [ex.submit(fetch_github_trending, lang) for lang in TRENDING_LANGS]
            + [ex.submit(fetch_hf_trending)]
            + [ex.submit(fetch_producthunt_ai)]
            + [ex.submit(fetch_hn_smart, HN_KEYWORDS)]
            + [ex.submit(fetch_paperswithcode_trending)]
        )
        all_items = [item for f in futures for item in f.result()]

    # arXiv: serialized to respect their 1-req-per-3-sec guideline
    for i, cat in enumerate(ARXIV_CATS):
        if i > 0:
            time.sleep(3)
        all_items.extend(fetch_arxiv(cat))

    scanned_count = len(all_items)
    print(f"📥 {scanned_count} items from past 7 days across all sources")
    if scanned_count == 0:
        print("Nothing new this week.")
        quality_logger.log_run("scout", items_scanned=0, total_cost_usd=0.0)
        return

    # Dedupe by content hash
    all_items, dedup_drops = dedupe(all_items)
    print(f"🧹 Dedup: dropped {dedup_drops} duplicates → {len(all_items)} unique")

    # Mem0 prior-filter
    all_items, mem0_drops = filter_by_mem0(all_items)
    print(f"🧠 Mem0 prior-filter: dropped {mem0_drops} already-evaluated → {len(all_items)} fresh")

    candidates_count = len(all_items)
    if candidates_count == 0:
        print("Everything was either duplicate or already in Mem0.")
        quality_logger.log_run(
            "scout", items_scanned=scanned_count, dedup_drops=dedup_drops,
            mem0_prior_drops=mem0_drops, candidates=0,
        )
        return

    print(f"\n🧠 Scoring {candidates_count} candidates with Sonnet 4.6 (cached system prompt)...")
    scored, score_cost = score_items(all_items)
    top = [item for item in scored if item.get("score", 0) >= 6][:12]
    if not top:
        print("No items scored ≥6. Lowering to top 4.")
        top = scored[:4]

    print(f"\n✨ Generating verdicts for {len(top)} items with Sonnet 4.6...")
    draft_verdicts, verdict_cost = generate_verdicts(top)

    print(f"\n⚖️  Judge pass — Opus 4.7 with extended thinking ({len(draft_verdicts)} drafts)...")
    judge_result, judge_cost = judge_mod.critique(draft_verdicts, scored)
    final_verdicts = judge_mod.apply_judge_decisions(draft_verdicts, scored, judge_result)
    n_vetoed = sum(1 for d in judge_result.get("decisions", []) if d.get("action") == "veto")
    n_retiered = sum(1 for d in judge_result.get("decisions", []) if d.get("action") == "retier")
    n_promoted = len(judge_result.get("missed", []))
    print(
        f"  Judge: kept {len(final_verdicts) - n_promoted}, vetoed {n_vetoed}, "
        f"retiered {n_retiered}, promoted {n_promoted} · "
        f"self-rating: {judge_result.get('quality_self_rating', 'medium')}"
    )
    print(f"  Summary: {judge_result.get('judge_summary', '')}")

    # Policy gates — deterministic content validation after the LLM judge.
    # See scripts/validators.py for the rule set.
    print("\n🛡  Policy gates...")
    final_verdicts, dropped_by_policy = validate_verdicts(final_verdicts, source_items=scored)
    if dropped_by_policy:
        for d in dropped_by_policy:
            tn = (d.get("verdict") or {}).get("tool_name", "?")
            print(f"  ❌ dropped {tn!r}: {d['reason']}")
    print(f"  Policy: {len(final_verdicts)} kept, {len(dropped_by_policy)} dropped")

    total_cost = score_cost + verdict_cost + judge_cost

    if not final_verdicts:
        print("⚠️  All drafts vetoed or dropped by policy. Nothing to publish.")
        quality_logger.log_run(
            "scout", items_scanned=scanned_count, dedup_drops=dedup_drops,
            mem0_prior_drops=mem0_drops, candidates=candidates_count,
            verdicts_pre_judge=len(draft_verdicts), verdicts_post_judge=0,
            vetoed=n_vetoed, tier_adjusted=n_retiered, missed_recovered=n_promoted,
            policy_dropped=len(dropped_by_policy),
            judge_self_rating=judge_result.get("quality_self_rating", "medium"),
            total_cost_usd=round(total_cost, 6),
            duration_s=round(time.time() - start, 2),
        )
        return

    briefing_path = write_briefing(
        final_verdicts, scanned_count, candidates_count, total_cost, judge_result,
    )
    print(f"\n📝 Briefing → {briefing_path}")

    print("🧠 Seeding Mem0...")
    seed_mem0(final_verdicts)

    print("📣 Posting to Slack...")
    today = datetime.now().strftime("%Y-%m-%d")
    duration = round(time.time() - start, 2)

    # Route: bot token + channel ID → threaded format (parent TL;DR + per-verdict
    # thread cards + auto-reactions). Otherwise fall back to single-message
    # (webhook-compatible).
    use_threaded = (
        os.environ.get("SLACK_BOT_TOKEN", "").startswith("xoxb-")
        and bool(os.environ.get("SLACK_CHANNEL_ID"))
    )
    delivery_meta: dict = {}
    try:
        if use_threaded:
            print("  → threaded format (bot token detected)")
            slack_post.weekly_briefing_threaded(
                date=today,
                scanned=scanned_count,
                cost=total_cost,
                verdicts=final_verdicts,
                judge_rating=judge_result.get("quality_self_rating", "medium"),
                judge_summary=judge_result.get("judge_summary", ""),
                dedup_drops=dedup_drops,
                prior_drops=mem0_drops,
                duration_s=duration,
            )
            delivery_meta = dict(slack_post.LAST_DELIVERY)
        else:
            print("  → single-message format (webhook or no bot token)")
            blocks = slack_post.weekly_briefing_blocks(
                date=today,
                scanned=scanned_count,
                cost=total_cost,
                verdicts=final_verdicts,
                judge_rating=judge_result.get("quality_self_rating", "medium"),
                judge_summary=judge_result.get("judge_summary", ""),
                dedup_drops=dedup_drops,
                prior_drops=mem0_drops,
            )
            slack_post.post(blocks)
        # Threaded mode: parent succeeded but threads may have failed.
        # Treat any thread failure as a partial-delivery flag, not full success.
        if delivery_meta:
            full_ok = (
                delivery_meta.get("parent", False)
                and delivery_meta.get("verdicts_failed", 0) == 0
                and delivery_meta.get("anchors_failed", 0) == 0
            )
            slack_ok = full_ok
        else:
            slack_ok = True
    except Exception as e:
        print(f"  Slack post failed: {e}")
        slack_ok = False

    quality_logger.log_run(
        "scout",
        items_scanned=scanned_count,
        dedup_drops=dedup_drops,
        mem0_prior_drops=mem0_drops,
        candidates=candidates_count,
        verdicts_pre_judge=len(draft_verdicts),
        verdicts_post_judge=len(final_verdicts),
        vetoed=n_vetoed,
        tier_adjusted=n_retiered,
        missed_recovered=n_promoted,
        policy_dropped=len(dropped_by_policy),
        judge_self_rating=judge_result.get("quality_self_rating", "medium"),
        total_cost_usd=round(total_cost, 6),
        duration_s=duration,
        slack_posted=slack_ok,
        slack_delivery=delivery_meta or None,
        judge_used_fallback=bool(judge_result.get("_judge_used_fallback")),
        llm_retries_total=LLM_STATS.total_retries,
        llm_retries_by_component=dict(LLM_STATS.by_component),
    )
    print(f"\n✅ Done. Run cost ${total_cost:.4f} · {duration}s · LLM retries: {LLM_STATS.total_retries}")


def main():
    """Top-level entry that always logs a row to quality-log.jsonl, even on crash."""
    start = time.time()
    try:
        _main_impl()
    except BaseException as exc:  # noqa: BLE001 — catch absolutely everything
        import traceback
        tb = traceback.format_exc()
        print(f"\n💥 Scout CRASHED: {type(exc).__name__}: {exc}", file=__import__("sys").stderr)
        print(tb, file=__import__("sys").stderr)
        quality_logger.log_run(
            "scout",
            crashed=True,
            error_type=type(exc).__name__,
            error_msg=str(exc)[:500],
            duration_s=round(time.time() - start, 2),
            llm_retries_total=LLM_STATS.total_retries,
            llm_retries_by_component=dict(LLM_STATS.by_component),
            last_retry_error=LLM_STATS.last_error,
        )
        raise


if __name__ == "__main__":
    main()
