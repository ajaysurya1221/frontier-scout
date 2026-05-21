"""
Tool-use JSON schemas for forcing structured outputs from Claude.

Instead of asking Claude to "reply with JSON" and parsing the text response,
we declare these as `tools` and set `tool_choice` to force the model to call
the named tool. The tool's `input` dict is guaranteed to match the schema —
no try/except, no regex, no JSON-in-markdown nightmares.
"""

# ── Scout pass 1: scoring ─────────────────────────────────────────────────────

SCORE_ITEMS_TOOL = {
    "name": "score_items",
    "description": (
        "Score each item 0-10 for relevance to the configured AI/ML stack and assign "
        "one of the six categories.\n"
        "\n"
        "  8-10 = directly affects our stack OR a major frontier drop (new model "
        "family, framework version with API changes, security/SOC2-relevant news, "
        "breakout-adoption tool we should have heard about earlier).\n"
        "  6-7  = adjacent — worth a verdict pass (TRIAL or ASSESS likely).\n"
        "  0-5  = noise. Keep out of the verdict pass. INCLUDES:\n"
        "    - Patch releases (x.y.Z bumps, hotfixes) with no API change\n"
        "    - Lockfile bumps, transitive-dependency hygiene, version-pin updates\n"
        "    - Test-suite, CI, or chore releases of frameworks we already use\n"
        "    - Survey papers / overview blog posts about hosted-model internals "
        "we don't control (no actionable lever for the team)\n"
        "    - Marketing posts, generic 'AI is transforming X' content\n"
        "    - JS-only / mobile-only ecosystems (we're Python)\n"
        "    - ProductHunt launches with no GitHub/PyPI presence\n"
        "    - Re-announcements of tools we've already evaluated this quarter\n"
        "    - Incident / breach / credential-leak news (e.g. 'X leaked keys on "
        "GitHub'). These are security advisories, not tools. Score ≤3.\n"
        "    - Op-ed / commentary / opinion posts about AI ethics, regulation, "
        "or industry takes with no specific tool/framework named. Score ≤4.\n"
        "\n"
        "Hygiene is not strategy. When in doubt about substance, score 5 and let "
        "it fall below the verdict threshold."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "Zero-based index of the item in the input list.",
                        },
                        "score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "frontier_model",
                                "orchestration",
                                "tool",
                                "data",
                                "compute",
                                "security",
                            ],
                        },
                    },
                    "required": ["index", "score", "category"],
                },
            },
        },
        "required": ["scores"],
    },
}


# ── Scout pass 2: verdict generation ──────────────────────────────────────────

VERDICT_TOOL = {
    "name": "emit_verdicts",
    "description": (
        "Emit a verdict for each item that warrants one. Follow the verdict template "
        "and match the gold exemplars in voice. SKIP items that don't warrant a verdict "
        "(patch releases, lockfile bumps, awareness-only items, solo-dev <6mo projects). "
        "Quality > quantity — better 4 sharp verdicts than 8 mixed ones."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "verdict": {
                            "type": "string",
                            "enum": ["adopt", "trial", "assess", "hold"],
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "frontier_model",
                                "orchestration",
                                "tool",
                                "data",
                                "compute",
                                "security",
                            ],
                        },
                        "soc2": {
                            "type": "string",
                            "enum": ["safe", "conditional", "blocked"],
                        },
                        "what": {
                            "type": "string",
                            "description": "One sentence — what the tool does.",
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": "Specific to the configured stack and compliance-sensitive workflow domain.",
                        },
                        "adoption_cost": {
                            "type": "string",
                            "description": "Concrete estimate + risk level (low/medium/high).",
                        },
                        "next_action": {
                            "type": "string",
                            "description": (
                                "Concrete next step with measurable timebox. "
                                "`lab <tool>` (30 min), `evaluate <tool>`, `Monitor 3 months`, "
                                "or a specific patch/swap action. Avoid 'awareness only' wording."
                            ),
                        },
                        "source_url": {
                            "type": "string",
                            "description": (
                                "Prefer the CANONICAL primary source. If the item came "
                                "from a blog/HN/aggregator about Tool X, set source_url "
                                "to Tool X's official URL (its GitHub repo, vendor blog "
                                "post, HuggingFace model page) — not the aggregator URL. "
                                "Falls back to the aggregator URL only if no primary source "
                                "is identifiable."
                            ),
                        },
                    },
                    "required": [
                        "tool_name",
                        "verdict",
                        "category",
                        "soc2",
                        "what",
                        "why_it_matters",
                        "adoption_cost",
                        "next_action",
                        "source_url",
                    ],
                },
            },
        },
        "required": ["verdicts"],
    },
}


# ── RLAIF Judge — Opus 4.7 with extended thinking ─────────────────────────────

JUDGE_TOOL = {
    "name": "critique_verdicts",
    "description": (
        "Critique the draft verdicts produced by the Sonnet verdict pass. You are "
        "the QUALITY GATE. Be strict but fair. Your output decides what ships to Slack.\n"
        "\n"
        "For each draft verdict, decide one of:\n"
        "  - keep      → the verdict is justified and lands in Slack as-is\n"
        "  - veto      → remove (e.g. patch-release-as-ADOPT, awareness-only-as-anything)\n"
        "  - retier    → keep the verdict but change the tier (e.g. ADOPT → TRIAL)\n"
        "\n"
        "Also: for each KEPT/RETIERED verdict, assign a `severity` (critical/high/standard) "
        "and a `readiness` score 0-5 (0=speculative, 5=production-proven big-lab-backed).\n"
        "\n"
        "Optionally, surface MISSED items that the verdict-gen passed over but you think "
        "deserve attention — only if they're clearly worth it (high stars, big-lab origin, "
        "or a stack-direct fit). Don't promote noise.\n"
        "\n"
        "Finish with quality_self_rating: high if you barely changed anything, low if you "
        "had to veto >40% of drafts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "description": "One entry per draft verdict (preserve their order/index).",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "Zero-based draft index."},
                        "action": {"type": "string", "enum": ["keep", "veto", "retier"]},
                        "reason": {"type": "string", "description": "One sentence rationale."},
                        "new_tier": {
                            "type": "string",
                            "enum": ["adopt", "trial", "assess", "hold"],
                            "description": "Required iff action=retier.",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "standard"],
                            "description": "Required iff action in (keep, retier).",
                        },
                        "readiness": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 5,
                            "description": "Required iff action in (keep, retier).",
                        },
                    },
                    "required": ["index", "action", "reason"],
                },
            },
            "missed": {
                "type": "array",
                "description": (
                    "Items the verdict-gen skipped but that you think deserve attention. "
                    "Only include if clearly worth it; empty list is the right default. "
                    "Produce a COMPLETE verdict for each — the briefing renders this directly."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "item_index": {
                            "type": "integer",
                            "description": "Zero-based index into the scored-items list.",
                        },
                        "tool_name": {"type": "string"},
                        "suggested_tier": {
                            "type": "string",
                            "enum": ["adopt", "trial", "assess", "hold"],
                        },
                        "soc2": {
                            "type": "string",
                            "enum": ["safe", "conditional", "blocked"],
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "frontier_model", "orchestration", "tool",
                                "data", "compute", "security",
                            ],
                        },
                        "what": {"type": "string", "description": "One sentence — what the tool does."},
                        "why_it_matters": {"type": "string"},
                        "adoption_cost": {"type": "string"},
                        "next_action": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "standard"],
                        },
                        "readiness": {"type": "integer", "minimum": 0, "maximum": 5},
                    },
                    "required": [
                        "item_index", "tool_name", "suggested_tier", "soc2",
                        "category", "what", "why_it_matters", "adoption_cost",
                        "next_action", "severity", "readiness",
                    ],
                },
            },
            "quality_self_rating": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": (
                    "Overall quality of the upstream verdict pass. "
                    "high = barely touched it; medium = a few adjustments; low = had to veto a lot."
                ),
            },
            "judge_summary": {
                "type": "string",
                "description": "1-2 sentences: what you saw and how the briefing reads now.",
            },
        },
        "required": ["decisions", "quality_self_rating", "judge_summary"],
    },
}


# ── Synthesizer ───────────────────────────────────────────────────────────────

SYNTHESIS_TOOL = {
    "name": "emit_synthesis",
    "description": (
        "Emit a structured monthly synthesis. Reference real entries from the "
        "radar and skills log. Be specific, not generic."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "exploration_summary": {
                "type": "string",
                "description": "2-3 sentences on themes and categories evaluated this month.",
            },
            "adopted": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tools that moved Trial → Adopt this month. Use [] if none.",
            },
            "stalled": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tools in Trial >6 weeks with no lab experiment. Name them.",
            },
            "blind_spots": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Important AI/ML categories with zero radar entries.",
            },
            "focus_this_month": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "rationale": {"type": "string"},
                    "lab_suggestion": {"type": "string"},
                },
                "required": ["tool", "rationale", "lab_suggestion"],
            },
            "org_opportunity": {
                "type": "string",
                "description": "One radar finding worth bringing to the engineering team this quarter.",
            },
        },
        "required": [
            "exploration_summary",
            "adopted",
            "stalled",
            "blind_spots",
            "focus_this_month",
            "org_opportunity",
        ],
    },
}


# ── ai-analyst skill — parallel tool use during `evaluate <tool>` ─────────────

EVALUATE_TOOLS = [
    {
        "name": "fetch_github_repo",
        "description": (
            "Fetch repo metadata: stars, last commit date, license, recent releases, open issues. "
            "Use to assess project health and license risk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "fetch_pypi_package",
        "description": "Fetch PyPI metadata: weekly downloads, version history, dependencies, license.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
            },
            "required": ["package"],
        },
    },
    {
        "name": "fetch_vendor_trust_portal",
        "description": (
            "Look up a vendor's SOC2 / ISO 27001 / FedRAMP status. Returns one of "
            "{certified, pending, none, unknown}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
            },
            "required": ["vendor"],
        },
    },
    {
        "name": "search_radar_memory",
        "description": (
            "Query Mem0 over past AI Telemetry verdicts. Use to check if this tool (or "
            "an alternative) has been evaluated before."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]
