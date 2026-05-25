"""
Deterministic policy gates that run AFTER the RLAIF judge, BEFORE any verdict
is written to the local SQLite store. These are content validators on top of
the structural tool-use schema — the schema enforces shape, these enforce
policy.

Motivation: the LLM-as-judge pass can be fooled by a confident generator (a
news-incident slipping in as ADOPT was the original failure mode). For an
unattended pipeline we want hard rails the model cannot cross regardless of
prompt drift.

Usage:
    from validators import validate_verdicts
    kept, dropped = validate_verdicts(final_verdicts, source_items=scored_items)
    for d in dropped:
        print(f"❌ {d['verdict']['tool_name']!r}: {d['reason']}")
"""

from __future__ import annotations

import difflib
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# Allowlist of domains the HTML/terminal renderers will hyperlink and the
# verdict schema will accept as source_url. Adding here is a policy
# decision — random vendor blogs don't belong on the list.
ALLOWED_DOMAINS = frozenset({
    # Code hosts the lab can actually pull from
    "github.com", "raw.githubusercontent.com", "githubusercontent.com",
    "gitlab.com", "pypi.org", "npmjs.com", "crates.io",
    # Model + tokenizer host
    "huggingface.co",
    # First-party labs / vendor blogs
    "anthropic.com", "openai.com", "deepmind.google",
    "deeplearning.ai", "mistral.ai", "blog.google", "google.com",
    # Practitioner blogs that publish high-signal tool releases
    "jack-clark.net", "latent.space", "simonwillison.net",
    "eugeneyan.com", "sebastianraschka.com", "aitidbits.ai",
    "cameronrwolfe.substack.com",
    # Community signal feeds
    "news.ycombinator.com", "ycombinator.com", "reddit.com",
    "paperswithcode.com", "arxiv.org", "producthunt.com",
    # Curated newsletters worth linking through
    "tldr.tech", "bensbites.co", "buttondown.com",
})


def domain_allowed(url: str) -> bool:
    """True iff the URL's domain is in ALLOWED_DOMAINS (incl. subdomains)."""
    try:
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return False
    if not netloc:
        return False
    return any(netloc == d or netloc.endswith("." + d) for d in ALLOWED_DOMAINS)


# Regex patterns for content rules
_INCIDENT_PATTERNS = re.compile(
    r"\b("
    r"leak(s|ed|ing)?"
    r"|breach(es|ed|ing)?"
    r"|expose(d|s|ing)?"
    r"|hack(ed|ing|s)?"
    r"|outage(s)?"
    r"|incident(s)?"
    r"|compromise[ds]?"
    r"|vulnerability|vulnerabilities|CVE-?\d"
    r"|0[- ]day|zero[- ]day"
    r")\b",
    re.I,
)
_FORUM_PREFIX = re.compile(r"^(Show|Ask|Tell|Launch)\s+HN\b", re.I)
_INJECTION_PATTERNS = re.compile(
    r"(ignore (the )?(previous|above) instructions"
    r"|disregard (the )?(system|rubric)"
    r"|you are now"
    r"|new (system )?instructions:)",
    re.I,
)
_PLACEHOLDER_PATTERNS = re.compile(
    r"(see source.*not generated|\(placeholder\)|^TODO$|^N/A$|^\(unknown\)$)",
    re.I,
)
_BAD_NEXT_ACTION = re.compile(r"^evaluate <\w{1,5}>$", re.I)
_SHELL_CHARS = re.compile(r"[;`]|\$\(")


VerdictTier = Literal["adopt", "trial", "assess", "hold"]
Risk = Literal["low", "medium", "high"]
Fit = Literal["high", "medium", "low"]
Category = Literal[
    "skill", "mcp_server", "agent_framework", "dev_tool", "model_drop",
]
Severity = Literal["critical", "high", "standard"]


class Verdict(BaseModel):
    """Pydantic model for a final verdict ready to render. Content-validated."""

    tool_name: str = Field(min_length=2, max_length=200)
    verdict: VerdictTier
    category: Category
    risk: Risk
    # ``fit`` is computed against the user's stack profile; verdicts produced
    # before a profile exists (or for items that don't intersect it) can
    # legitimately omit it.
    fit: Fit | None = None
    what: str = Field(min_length=20, max_length=240)
    why_this_week: str | None = Field(default=None, max_length=180)
    why_it_matters: str = Field(min_length=20, max_length=420)
    adoption_cost: str = Field(min_length=4, max_length=220)
    next_action: str = Field(min_length=12, max_length=220)
    source_url: str = Field(min_length=8, max_length=500)
    severity: Severity | None = None
    readiness: int | None = Field(default=None, ge=0, le=5)
    permission_risk: Risk | None = None
    evidence: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("tool_name")
    @classmethod
    def tool_name_not_event(cls, v: str) -> str:
        if _INCIDENT_PATTERNS.search(v):
            raise ValueError(f"tool_name looks like an event/incident headline: {v!r}")
        if _FORUM_PREFIX.search(v):
            raise ValueError(f"tool_name has HN forum prefix not stripped: {v!r}")
        if "stars this week" in v.lower() or "stars today" in v.lower():
            raise ValueError(f"tool_name contains trending-suffix noise: {v!r}")
        if not re.search(r"\w", v):
            raise ValueError(f"tool_name has no word characters: {v!r}")
        return v.strip()

    @field_validator("adoption_cost")
    @classmethod
    def no_placeholder(cls, v: str) -> str:
        if _PLACEHOLDER_PATTERNS.search(v):
            raise ValueError(f"adoption_cost contains placeholder text: {v!r}")
        return v

    @field_validator("next_action")
    @classmethod
    def next_action_concrete(cls, v: str) -> str:
        if _BAD_NEXT_ACTION.match(v):
            raise ValueError(f"next_action has truncated tool name: {v!r}")
        low = v.lower()
        if "awareness only" in low or "0 cost — awareness" in low:
            raise ValueError(f"next_action is awareness-only (not actionable): {v!r}")
        return v

    @field_validator("source_url")
    @classmethod
    def url_safe(cls, v: str) -> str:
        if _SHELL_CHARS.search(v):
            raise ValueError(f"source_url contains shell-style chars: {v!r}")
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"source_url scheme not http/https: {v!r}")
        if not parsed.netloc:
            raise ValueError(f"source_url has no domain: {v!r}")
        if not domain_allowed(v):
            raise ValueError(f"source_url domain not in allowlist: {parsed.netloc}")
        return v

    @field_validator("what", "why_it_matters", "why_this_week")
    @classmethod
    def no_injection(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if _INJECTION_PATTERNS.search(v):
            raise ValueError(f"prose contains prompt-injection signature: {v[:80]!r}")
        return v

    @model_validator(mode="after")
    def adopt_requires_readiness(self) -> "Verdict":
        if self.verdict == "adopt" and self.readiness is not None and self.readiness < 3:
            # Soft demote: keep the verdict but log via a sentinel; caller
            # handles the tier-flip. We don't raise here because losing the
            # verdict entirely is more damaging than re-tiering it.
            object.__setattr__(self, "_demoted_to", "trial")
        return self


def _fuzzy_tool_in_sources(tool_name: str, source_items: list[dict]) -> bool:
    """True if tool_name fuzzy-matches at least one source item's title.

    Uses difflib ratio with a low threshold; the model shouldn't invent tool
    names out of thin air. Threshold 0.4 is intentionally permissive (handles
    "obra/superpowers" matching a title that says "obra/superpowers — 10K stars").
    """
    if not source_items:
        return True  # no sources to check against → can't enforce
    needle = tool_name.lower().strip()
    if not needle:
        return False
    for it in source_items:
        title = (it.get("title") or "").lower()
        if not title:
            continue
        if needle in title or title in needle:
            return True
        ratio = difflib.SequenceMatcher(None, needle, title).ratio()
        if ratio >= 0.4:
            return True
    return False


def validate_verdicts(
    raw_verdicts: list[dict],
    source_items: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Run policy gates over the post-judge verdict list.

    Returns:
        (kept, dropped)
        kept: list of verdict dicts ready to render. ADOPT verdicts with
              readiness < 3 are auto-demoted to TRIAL with `_demoted` reason.
        dropped: list of {verdict: <original_dict>, reason: str} for the log.
    """
    source_items = source_items or []
    kept: list[dict] = []
    dropped: list[dict] = []

    for v in raw_verdicts:
        try:
            model = Verdict(**v)
        except ValidationError as e:
            reasons = "; ".join(
                err.get("msg", "") for err in e.errors() if err.get("msg")
            )
            dropped.append({"verdict": v, "reason": reasons or "schema invalid"})
            continue

        # Fuzzy match the tool_name against the input pool (defense vs.
        # hallucinated names).
        if not _fuzzy_tool_in_sources(model.tool_name, source_items):
            dropped.append({
                "verdict": v,
                "reason": (
                    f"tool_name {model.tool_name!r} not found in any source title — "
                    "model may have invented or paraphrased it"
                ),
            })
            continue

        out = model.model_dump()
        # Handle the soft-demote from adopt_requires_readiness
        demoted_to = getattr(model, "_demoted_to", None)
        if demoted_to:
            out["verdict"] = demoted_to
            out["_policy_demoted_from"] = "adopt"

        kept.append(out)

    return kept, dropped
