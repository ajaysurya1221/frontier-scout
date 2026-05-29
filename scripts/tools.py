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
        "      Exception: releases classified as security or hardening, or "
        "breaking changes for dependencies in the active repo profile, are "
        "not patch noise.\n"
        "    - Survey papers / overview blog posts with no shipping code\n"
        "    - Marketing posts, generic 'AI is transforming X' content\n"
        "    - Incident / breach / credential-leak news (these are security "
        "advisories, not tools — score ≤ 3).\n"
        "    - Op-ed / commentary / opinion posts about AI ethics or industry "
        "takes with no specific tool / framework named (score ≤ 4).\n"
        "    - Re-announcements of tools already in the user's seen-tools set.\n"
        "    - General-purpose infrastructure with NO AI / agent / LLM surface: "
        "web frameworks (FastAPI, Flask, Django, Express, Next.js), HTTP "
        "clients (requests, httpx, axios), ORMs / DB drivers (SQLAlchemy, "
        "Prisma), build / bundler / lint tooling (webpack, vite, ruff, eslint), "
        "and similar plumbing. Frontier Scout is an AI-ADOPTION RADAR — these "
        "belong in the dependency scan, NOT the AI-tools feed. Score ≤ 4 even "
        "when the framework appears in the user's stack profile. EXCEPTION: a "
        "release that adds a FIRST-CLASS AI / agent / LLM capability (native "
        "tool-calling, a built-in MCP endpoint, streaming LLM responses, an "
        "agent runtime) is in-scope — score it on merit and tag it.\n"
        "\n"
        "AI-RADAR SCOPE: an item only deserves a score ≥ 6 if it is AI-NATIVE — "
        "it is a skill, MCP server, agent framework, model release, or a "
        "developer tool whose primary purpose is building / running / evaluating "
        "AI or agentic systems. A generic library that merely happens to sit in "
        "an AI project's dependency tree is not AI-native.\n"
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
                        "permission_risk": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": (
                                "Optional. Local permission risk if the item clearly asks "
                                "for repo, shell, browser, network, or credential access."
                            ),
                        },
                        "evidence": {
                            "type": "array",
                            "description": (
                                "Optional short source-backed evidence bullets for future "
                                "Adoption Firewall receipts."
                            ),
                            "items": {"type": "string"},
                            "maxItems": 5,
                        },
                        # v1.2.1 — Stream K: concern fields. The TUI's
                        # Scout-tab detail panel renders these as a
                        # "Concerns" section so the user always knows
                        # *why* we'd push back on adoption. All four are
                        # optional; missing fields are treated as
                        # "unknown" and the corresponding concern rule
                        # gracefully skips.
                        "cost_per_call_usd": {
                            "type": "number",
                            "description": (
                                "Optional. Best-effort per-call cost on the user's "
                                "API key. Use 0 for tools that run fully locally. "
                                "Omit entirely if cost is not metered or unknown — "
                                "never guess a number."
                            ),
                            "minimum": 0,
                        },
                        "last_release_age_days": {
                            "type": "integer",
                            "description": (
                                "Optional. Days since the most recent release of "
                                "this tool/model/package. Used to flag abandoned "
                                "projects. Omit if unknown."
                            ),
                            "minimum": 0,
                        },
                        "release_url": {
                            "type": "string",
                            "maxLength": 500,
                            "description": (
                                "Optional. Deep link to the most recent release "
                                "(GitHub release, HuggingFace model card, etc.)."
                            ),
                        },
                        "lock_in_risk": {
                            "type": "string",
                            "enum": ["none", "low", "medium", "high"],
                            "description": (
                                "Optional. How hard it would be to switch away "
                                "later. 'none' = open spec + multiple impls; "
                                "'high' = vendor-proprietary API surface."
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


CLASSIFY_RELEASE_TOOL = {
    "name": "classify_release",
    "description": (
        "Classify release-note text for repo-relevant dependency intelligence. "
        "Return security/hardening/breaking only when the evidence quote directly "
        "supports that label; otherwise use feature or noise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["security", "hardening", "breaking", "feature", "noise"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_quotes": {
                "type": "array",
                "items": {"type": "string", "maxLength": 220},
                "maxItems": 4,
            },
        },
        "required": ["category", "confidence", "evidence_quotes"],
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
            # v1.2.1 — Stream K: grade concern accuracy. The Scout tab
            # renders deterministic concern rules client-side, but the
            # judge is the one who notices when a verdict is silently
            # missing a "security_surface" or "token_burn" that should
            # have been flagged. Empty list when the upstream pass
            # got concerns right.
            "concern_audits": {
                "type": "array",
                "description": (
                    "Optional list of concern-accuracy complaints against "
                    "the upstream verdict pass. Mention only material "
                    "misses (a missing security_surface on a write-capable "
                    "tool; a missing token_burn on a model_drop). The "
                    "Scout UI surfaces these to the user so they trust the "
                    "concern chips."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "verdict_index": {
                            "type": "integer",
                            "description": "Zero-based index into the draft verdicts.",
                        },
                        "missing_concern_slug": {
                            "type": "string",
                            "enum": [
                                "weak_fit",
                                "token_burn",
                                "abandoned",
                                "security_surface",
                                "vendor_lock_in",
                                "marketing_only",
                                "unproven",
                            ],
                        },
                        "evidence": {
                            "type": "string",
                            "description": "One sentence: why this concern should fire.",
                        },
                    },
                    "required": ["verdict_index", "missing_concern_slug", "evidence"],
                },
            },
        },
        "required": ["decisions", "quality_self_rating", "judge_summary"],
    },
}
