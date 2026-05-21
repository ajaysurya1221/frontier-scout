"""
Channel taste model — feedback-driven preference learning.

Reads the append-only signal ledger (`signals-log.jsonl`), applies exponential
time decay (half-life 14 days), and emits a normalised preferences snapshot
(`preferences.json`).

Two consumers:

1. **Scout's `score_items()`** — calls `format_team_prefs_paragraph()` to
   build a short "Team preferences" paragraph that gets injected into the
   scoring system prompt (Sonnet-aware steering), and `reweight_score()`
   to apply a bounded math multiplier after Sonnet returns its 0–10 score
   (post-scoring rail).

2. **`scripts/slack_post.py`** — calls `load()` and reads the
   `signal_count_14d` field to render the "📈 Tuned by N reactions" line
   in the briefing TL;DR.

Cold-start safety: when `signal_count_14d < COLD_START_THRESHOLD` (10) the
caller is expected to bypass both steering paths so behaviour stays
identical to a fresh repo.

Signal weight calibration is documented in `signals-log.jsonl` and lives at
`SIGNAL_WEIGHTS` below. Adjust there if reactions feel under- or
over-weighted relative to button clicks.

This module is pure-stdlib by design. No model calls, no network, no Mem0.
Easy to unit-test and re-derivable from the ledger at any time.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SIGNALS_LOG = REPO_ROOT / "signals-log.jsonl"
PREFERENCES = REPO_ROOT / "preferences.json"

# Half-life in days. A reaction from 14 days ago contributes half as much as
# a reaction from today. Tuned for a weekly briefing cadence — recent
# reactions matter more, but a single noisy day can't dominate.
HALF_LIFE_DAYS = 14.0

# Below this many signals in the last 14 days, the system reverts to
# pre-personalisation behaviour. Avoids overreacting to thin data.
COLD_START_THRESHOLD = 10

# Multiplier scale. α=0.1 means each tag at +1.0 contributes a 10% nudge.
#
# Clamp is ASYMMETRIC by design: the taste model can promote things the
# team likes (up to +50%) but can only gently dampen things they haven't
# reacted to (down to -20%). The exploration/exploitation insurance:
# adjacent items get lifted, but a strong-but-unfamiliar tag can never
# be silenced. A score of 9 dampens at worst to 7.2, not 4.5.
ALPHA = 0.1
MULTIPLIER_MIN = 0.8   # max dampen = -20%
MULTIPLIER_MAX = 1.5   # max boost  = +50%

# Items with a base score at or above this threshold bypass the reweight
# entirely. Rationale: when Sonnet (with no team-prefs input — recall the
# prompt injection comes ALONGSIDE the scoring) emits an 8+ rating, that
# absolute signal is strong enough to override team taste. We don't want
# a niche-topic 9/10 to slip below an on-trend 7/10.
HIGH_BASE_PRESERVATION = 8.0

# Categories that always pass through unchanged. Frontier-model drops and
# security advisories are non-negotiable — the team's taste model is for
# the "tools & frameworks" middle of the radar, not for stack-shifting
# releases or security gates.
CATEGORY_BYPASS = frozenset({"frontier_model", "security"})

# Per-user-per-tag absolute cap on contribution magnitude. A single user
# can contribute at most ±MAX_PER_USER_GROSS (in raw signal-weight units)
# to any one tag, regardless of how many times they react. Stops one vocal
# voter from skewing weights across many messages on the same topic.
#
# 3.0 ≈ three thumbsups' worth — after three reactions on the same tag
# from the same person, additional reactions stop accumulating influence.
MAX_PER_USER_GROSS = 3.0

# Canonical signal weights. Keep in sync with `lambda/button_dispatch.py`
# and `lambda/reaction_dispatch.py` (the emitters). Signals with type not
# in this table are ignored.
SIGNAL_WEIGHTS: dict[str, float] = {
    "lab_queued":              +3.0,   # 🧪 click
    "evaluate_requested":      +2.0,   # 📚 click
    "reaction_thumbsup":       +1.0,   # 👍
    "thread_reply":            +0.5,
    "compare_opened":          +0.3,   # 📊 click
    "reaction_test_tube":      +1.0,   # human-added 🧪 reaction
    "reaction_thumbsdown":     -1.0,   # 👎
    "snoozed":                 -2.0,
    "marked_seen":             -0.5,
}


# ── Public API ───────────────────────────────────────────────────────────────

def load() -> dict:
    """Return the latest preferences snapshot, or a cold-start placeholder.

    Reading order:
      1. preferences.json if it exists
      2. otherwise regenerate from signals-log.jsonl on the fly
      3. otherwise return a sentinel with signal_count_14d=0
    """
    if PREFERENCES.exists():
        try:
            return json.loads(PREFERENCES.read_text())
        except json.JSONDecodeError:
            pass  # corrupted — fall through to regenerate
    return regenerate()


def regenerate(now: datetime | None = None) -> dict:
    """Re-derive preferences from signals-log.jsonl and persist them.

    `now` is injectable for tests.
    """
    now = now or datetime.now(timezone.utc)
    signals = load_signals()
    prefs = aggregate(signals, now=now)
    save(prefs)
    return prefs


def load_signals() -> list[dict]:
    """Read the append-only signal ledger. Returns [] if the file is missing
    or empty. Lines that fail to parse are skipped with a warning printed
    to stdout (preserves the run; one bad write shouldn't poison the model).
    """
    if not SIGNALS_LOG.exists():
        return []
    out: list[dict] = []
    for line_no, line in enumerate(SIGNALS_LOG.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"  ⚠️ signals-log.jsonl line {line_no}: {e}; skipping")
    return out


def save(prefs: dict) -> None:
    """Persist a preferences snapshot, sort-keyed for stable diffs."""
    PREFERENCES.write_text(json.dumps(prefs, indent=2, sort_keys=True) + "\n")


# ── Aggregation ──────────────────────────────────────────────────────────────

def aggregate(signals: list[dict], now: datetime | None = None) -> dict:
    """Time-decay signals into per-category and per-tag weights ∈ [-1, +1].

    Algorithm:
      1. For each signal, compute the time-decayed weight:
            w = SIGNAL_WEIGHTS[signal_type] * exp(-ln(2) * age_days / HALF_LIFE)
      2. Group signals by tag and by category; sum decayed weights.
      3. Apply per-user cap: any single user's contribution to a tag is
         clipped to PER_USER_CAP × (sum of absolute weights for that tag).
      4. Normalise: divide each tag's net weight by the max absolute weight
         across all tags, yielding a value in [-1, +1]. Same for categories.
      5. Drop tags with |weight| < 0.05 after normalisation (noise floor).
    """
    now = now or datetime.now(timezone.utc)

    # Counters (gross) for visibility metrics surfaced in the TL;DR.
    signal_count_14d = 0
    reaction_count_14d = 0
    lab_count_14d = 0

    # Per-tag, per-user gross weight (for the per-user cap).
    tag_user_gross: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    category_user_gross: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for s in signals:
        kind = s.get("signal")
        if kind not in SIGNAL_WEIGHTS:
            continue
        ts = _parse_ts(s.get("ts"))
        if ts is None:
            continue
        age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
        if age_days < 14.0:
            signal_count_14d += 1
            if kind.startswith("reaction_"):
                reaction_count_14d += 1
            if kind == "lab_queued":
                lab_count_14d += 1
        decay = math.exp(-math.log(2.0) * age_days / HALF_LIFE_DAYS)
        # `removed` flips the sign — undoing a 👍 must cancel the original
        # +1.0, not reinforce it. The Lambda reaction dispatcher records the
        # original signal name on Slack's `reaction_removed` event and sets
        # this flag; the aggregator is the source of truth for the inversion.
        sign = -1.0 if s.get("removed") else 1.0
        raw_weight = SIGNAL_WEIGHTS[kind] * decay * sign

        user = s.get("user") or "anon"
        for tag in (s.get("tags") or []):
            if isinstance(tag, str) and tag:
                tag_user_gross[tag.lower()][user] += raw_weight
        cat = s.get("category")
        if isinstance(cat, str) and cat:
            category_user_gross[cat.lower()][user] += raw_weight

    # Apply per-user cap and sum into net weights.
    tag_net = _cap_and_sum(tag_user_gross)
    category_net = _cap_and_sum(category_user_gross)

    # Normalise into [-1, +1].
    tags_norm = _normalise(tag_net, noise_floor=0.05)
    categories_norm = _normalise(category_net, noise_floor=0.05)

    return {
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "signal_count_14d": signal_count_14d,
        "reaction_count_14d": reaction_count_14d,
        "lab_count_14d": lab_count_14d,
        "categories": categories_norm,
        "tags": tags_norm,
    }


def _parse_ts(s) -> datetime | None:
    """Parse an ISO-8601 timestamp; tolerate trailing Z."""
    if not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


def _cap_and_sum(user_gross: dict[str, dict[str, float]]) -> dict[str, float]:
    """Apply per-user absolute cap, then sum into net per-key weight.

    Each user's contribution to a single tag is clipped to ±MAX_PER_USER_GROSS.
    Sign is preserved (a user who reacts thumbsup 100 times still produces a
    positive contribution — just capped at MAX_PER_USER_GROSS).
    """
    out: dict[str, float] = {}
    for key, per_user in user_gross.items():
        capped_total = 0.0
        for w in per_user.values():
            sign = 1.0 if w >= 0 else -1.0
            capped_total += sign * min(abs(w), MAX_PER_USER_GROSS)
        out[key] = capped_total
    return out


def _normalise(net: dict[str, float], noise_floor: float) -> dict[str, float]:
    """Scale into [-1, +1] by dividing by max absolute weight. Drop ≈zero."""
    if not net:
        return {}
    peak = max(abs(v) for v in net.values()) or 1.0
    return {
        k: round(v / peak, 3)
        for k, v in net.items()
        if abs(v / peak) >= noise_floor
    }


# ── Prompt-injection paragraph (Sonnet-aware steering) ───────────────────────

def format_team_prefs_paragraph(prefs: dict | None = None) -> str:
    """Render a one-paragraph "Team preferences" block for the scoring prompt.

    Returns an empty string when the system is in cold-start mode — callers
    can safely concatenate the result with no extra branching.
    """
    prefs = prefs if prefs is not None else load()
    if prefs.get("signal_count_14d", 0) < COLD_START_THRESHOLD:
        return ""

    tags = prefs.get("tags", {}) or {}
    if not tags:
        return ""

    higher = sorted(((k, v) for k, v in tags.items() if v >= 0.40),
                    key=lambda kv: -kv[1])[:6]
    mild = sorted(((k, v) for k, v in tags.items() if 0.10 <= v < 0.40),
                  key=lambda kv: -kv[1])[:6]
    lower = sorted(((k, v) for k, v in tags.items() if -0.40 < v <= -0.10),
                   key=lambda kv: kv[1])[:6]
    avoid = sorted(((k, v) for k, v in tags.items() if v <= -0.40),
                   key=lambda kv: kv[1])[:6]

    lines = [
        "## Team preferences "
        f"(learned from {prefs['signal_count_14d']} reactions over the last 14 days)",
    ]
    if higher:
        lines.append("Higher interest:  " + ", ".join(t for t, _ in higher))
    if mild:
        lines.append("Mild interest:    " + ", ".join(t for t, _ in mild))
    if lower:
        lines.append("Lower interest:   " + ", ".join(t for t, _ in lower))
    if avoid:
        lines.append("Strong avoid:     " + ", ".join(t for t, _ in avoid))
    lines.append(
        "Treat as soft context for BORDERLINE items only. NOVELTY and SEVERITY "
        "always take precedence: never downweight a major frontier-model release, "
        "security advisory, or any item you would otherwise score 8+ based on "
        "team preferences. The goal is to LIFT adjacent items the team cares "
        "about, never to silence items they haven't reacted to yet."
    )
    return "\n".join(lines)


# ── Math-bounded post-scoring reweight ───────────────────────────────────────

def reweight_score(base_score: float, tags: list[str] | None,
                   prefs: dict | None = None,
                   category: str | None = None) -> float:
    """Apply the bounded multiplier to a single item's base score.

    Three exploration safeguards bypass the reweight entirely:
      1. Cold start (<10 signals in 14d) — no model yet
      2. base_score ≥ 8 — strong absolute signal dominates team taste
      3. category in CATEGORY_BYPASS — frontier-model + security
         releases are non-negotiable, never dampened

    Outside the bypasses, the multiplier is asymmetrically clipped to
    [0.8x, 1.5x] — boosts up to +50%, dampens only to −20%. This means
    a contrarian or unfamiliar-tag signal can never silence an item Sonnet
    rated well; the taste model lifts, but never kills.
    """
    prefs = prefs if prefs is not None else load()
    if prefs.get("signal_count_14d", 0) < COLD_START_THRESHOLD:
        return base_score
    if base_score >= HIGH_BASE_PRESERVATION:
        return base_score
    if category and category in CATEGORY_BYPASS:
        return base_score
    if not tags:
        return base_score

    tag_weights = prefs.get("tags", {}) or {}
    boost = sum(tag_weights.get(t.lower(), 0.0) for t in tags) * ALPHA
    multiplier = max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, 1.0 + boost))
    return base_score * multiplier


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # `python scripts/preferences.py` — regenerate and print summary.
    prefs = regenerate()
    print(json.dumps(prefs, indent=2, sort_keys=True))
    print()
    para = format_team_prefs_paragraph(prefs)
    if para:
        print("--- prompt injection preview ---")
        print(para)
    else:
        print(f"(cold start — {prefs['signal_count_14d']} signals "
              f"< threshold {COLD_START_THRESHOLD})")
