"""Tool-use JSON schemas for forcing structured outputs from Claude.

We declare these as Anthropic ``tools`` with ``tool_choice`` pinning the
named tool — the model can't drift into prose, the input dict is
guaranteed to match the schema, and downstream Pydantic gates can run
without parse heroics.
"""

# Categories used across the score + verdict + judge tools. Keep in lockstep
# with ``validators.Category`` — adding a new category means editing both.
_CATEGORY_ENUM = [
    "skill",
    "mcp_server",
    "agent_framework",
    "dev_tool",
    "model_drop",
]


# ── Pass 1: scoring ─────────────────────────────────────────────────────────

SCORE_ITEMS_TOOL = {
    "name": "score_items",
    "description": (
        "Score each item 0-10 for relevance to the configured stack profile "
        "and assign one of the five categories.\n"
        "\n"
        "  8-10 = direct hit on the stack profile, OR a major frontier drop "
        "(new model family, framework version with API changes, breakout-"
        "adoption tool the user should have heard about earlier).\n"
        "  6-7  = adjacent — worth a verdict pass (TRIAL or ASSESS likely).\n"
        "  0-5  = noise. Keep out of the verdict pass. INCLUDES:\n"
        "    - Patch releases (x.y.Z bumps, hotfixes) with no API change\n"
        "    - Lockfile bumps, transitive-dependency hygiene, version-pin updates\n"
        "    - Survey papers / overview blog posts with no shipping code\n"
        "    - Marketing posts, generic 'AI is transforming X' content\n"
        "    - Incident / breach / credential-leak news (these are security "
        "advisories, not tools — score ≤ 3).\n"
        "    - Op-ed / commentary / opinion posts about AI ethics or industry "
        "takes with no specific tool / framework named (score ≤ 4).\n"
        "    - Re-announcements of tools already in the user's seen-tools set.\n"
        "\n"
        "Hygiene is not strategy. When in doubt about substance, score 5 and "
        "let it fall below the verdict threshold."
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
                            "enum": _CATEGORY_ENUM,
                        },
                        "tags": {
                            "type": "array",
                            "description": (
                                "OPTIONAL: 0–3 short kebab-case topic tags describing "
                                "the item (e.g. 'mcp', 'agentic-coding', 'evals', "
                                "'long-context', 'rag', 'fine-tuning', 'vector-search'). "
                                "Used by future taste-model layers. Lowercase, hyphen-"
                                "separated, no spaces. Skip (return []) when running "
                                "tight on output tokens."
                            ),
                            "items": {"type": "string"},
                            "minItems": 0,
                            "maxItems": 3,
                        },
                    },
                    "required": ["index", "score", "category"],
                },
            },
        },
        "required": ["scores"],
    },
}


# ── Pass 2: verdict generation ──────────────────────────────────────────────

VERDICT_TOOL = {
    "name": "emit_verdicts",
    "description": (
        "Emit a verdict for each item that warrants one. Follow the verdict template "
        "and match the gold exemplars in voice. SKIP items that don't warrant a "
        "verdict (patch releases, lockfile bumps, awareness-only items, solo-"
        "developer projects under 6 months old). Quality > quantity — better 4 "
        "sharp verdicts than 8 mixed ones."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "minLength": 2,
                            "maxLength": 120,
                        },
                        "verdict": {
                            "type": "string",
                            "enum": ["adopt", "trial", "assess", "hold"],
                        },
                        "category": {
                            "type": "string",
                            "enum": _CATEGORY_ENUM,
                        },
                        "risk": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": (
                                "Cost of being wrong about this tool. See RISK_RUBRIC "
                                "in the system prompt; raise the level when in doubt."
                            ),
                        },
                        "fit": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": (
                                "Optional. Set ONLY if you can name at least one element "
                                "from STACK_PROFILE this tool plugs into. Omit when the "
                                "profile is empty or the tool is universal. NEVER guess."
                            ),
                        },
                        "what": {
                            "type": "string",
                            "description": "One sentence — what the tool does.",
                            "minLength": 20,
                            "maxLength": 240,
                        },
                        "why_this_week": {
                            "type": "string",
                            "description": (
                                "Optional timing signal (release, adoption spike, or "
                                "security event). Omit or set empty string when timing "
                                "is not meaningful."
                            ),
                            "maxLength": 180,
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": (
                                "Specific to the configured STACK_PROFILE. If the "
                                "profile is empty, write a single sentence on universal "
                                "merit instead — and downgrade the verdict tier accordingly."
                            ),
                            "minLength": 20,
                            "maxLength": 420,
                        },
                        "adoption_cost": {
                            "type": "string",
                            "description": "Concrete estimate + risk level (low / medium / high).",
                            "minLength": 4,
                            "maxLength": 220,
                        },
                        "next_action": {
                            "type": "string",
                            "description": (
                                "Concrete next step with measurable timebox. "
                                "`lab <tool>` (one try-before-install run), "
                                "`compare <tool>`, `Monitor 3 months`, or a specific "
                                "swap / patch action. Avoid 'awareness only' wording."
                            ),
                            "minLength": 12,
                            "maxLength": 220,
                        },
                        "source_url": {
                            "type": "string",
                            "maxLength": 500,
                            "description": (
                                "Prefer the CANONICAL primary source. If the item came "
                                "from a blog / HN / aggregator about Tool X, set "
                                "source_url to Tool X's official URL (its GitHub repo, "
                                "vendor blog post, HuggingFace model page) — not the "
                                "aggregator URL. Falls back to the aggregator URL only "
                                "if no primary source is identifiable."
                            ),
                        },
                    },
                    "required": [
                        "tool_name",
                        "verdict",
                        "category",
                        "risk",
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


# ── Pass 3 (optional): Opus 4.7 RLAIF judge ─────────────────────────────────

JUDGE_TOOL = {
    "name": "critique_verdicts",
    "description": (
        "Critique the draft verdicts produced by the Sonnet verdict pass. You are "
        "the QUALITY GATE. Be strict but fair. Your output decides what is written "
        "to the user's local SQLite store and surfaced via the Claude Code skill.\n"
        "\n"
        "For each draft verdict, decide one of:\n"
        "  - keep      → the verdict is justified and lands as-is\n"
        "  - veto      → remove (e.g. patch-release-as-ADOPT, awareness-only-as-anything)\n"
        "  - retier    → keep the verdict but change the tier (e.g. ADOPT → TRIAL)\n"
        "\n"
        "Also: for each KEPT/RETIERED verdict, assign a `severity` (critical / high / "
        "standard) and a `readiness` score 0-5 (0=speculative, 5=production-proven "
        "big-lab-backed).\n"
        "\n"
        "Optionally, surface MISSED items the verdict-gen passed over but you think "
        "deserve attention — only if they're clearly worth it (high stars, big-lab "
        "origin, or a stack-direct fit). Don't promote noise.\n"
        "\n"
        "Finish with quality_self_rating: high if you barely changed anything, low if "
        "you had to veto > 40% of drafts."
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
                        "index": {
                            "type": "integer",
                            "description": "Zero-based draft index.",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["keep", "veto", "retier"],
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence rationale.",
                        },
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
                    "Items the verdict-gen skipped but that you think deserve "
                    "attention. Only include if clearly worth it; empty list is "
                    "the right default. Produce a COMPLETE verdict for each."
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
                        "risk": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "fit": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Optional — see VERDICT_TOOL.fit.",
                        },
                        "category": {
                            "type": "string",
                            "enum": _CATEGORY_ENUM,
                        },
                        "what": {"type": "string", "description": "One sentence — what the tool does."},
                        "why_it_matters": {"type": "string"},
                        "adoption_cost": {"type": "string"},
                        "next_action": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "standard"],
                        },
                        "readiness": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 5,
                        },
                    },
                    "required": [
                        "item_index",
                        "tool_name",
                        "suggested_tier",
                        "risk",
                        "category",
                        "what",
                        "why_it_matters",
                        "adoption_cost",
                        "next_action",
                        "severity",
                        "readiness",
                    ],
                },
            },
            "quality_self_rating": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": (
                    "Overall quality of the upstream verdict pass. "
                    "high = barely touched it; medium = a few adjustments; "
                    "low = had to veto a lot."
                ),
            },
            "judge_summary": {
                "type": "string",
                "description": "1-2 sentences: what you saw and how the run reads now.",
            },
        },
        "required": ["decisions", "quality_self_rating", "judge_summary"],
    },
}
