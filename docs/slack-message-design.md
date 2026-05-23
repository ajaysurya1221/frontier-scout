# Slack Message Design Guide

This project renders AI-generated intelligence into deterministic Slack Block Kit.
The quality bar is production-facing engineering communication, not chatbot chatter.

## Message Anatomy

Every primary message should make these obvious in the first screenful:

1. **What happened**: funnel + decision summary.
2. **Why it matters**: short impact statement tied to stack/risk.
3. **What to do next**: concrete actions with timeboxes.

Recommended structure for weekly parent posts:

- `header`: briefing title + date.
- `section`: three labeled parts (`What happened`, `Why it matters`, `What to do next`).
- `section.fields`: pipeline metrics + decision mix.
- `rich_text_list` (ordered): top findings only.
- `context`: lightweight command hints.

Recommended structure for thread verdict cards:

- Hero (`section`): tool + textual tier badge + SOC2 + readiness.
- `section`: concise `Why it matters`.
- `section.fields`: `Adoption cost` + `Next action`.
- Optional `context`: short notes (`Why now`, memory trend, source-warning).
- Top-level `actions` block for interactive controls.

## Markdown / Block Kit Rules

- Use Slack `mrkdwn`; do not assume GitHub markdown behavior.
- Escape `&`, `<`, `>` in model text before rendering.
- Keep block text bounded; truncate long prose deterministically.
- Keep overflow option values compact and below Slack limits.
- Do **not** include unsupported fields in Block Kit elements.
  - Example: overflow options must not contain `confirm` (Slack rejects with `invalid_blocks`).

## Good vs Bad Patterns

Good:

- Short labeled sections with clear hierarchy.
- Top findings as ordered, scannable list.
- Tier state shown in text and not only by color.
- Descriptive fallback text for notifications and screen readers.

Bad:

- Dense walls of context text.
- Unbounded italicized paragraphs from model output.
- Repeating full verdict detail in both parent and thread.
- Emoji-heavy label prefixes replacing real structure.
- Generic fallback text like `Frontier Scout update`.

## Screenshot-Driven QA Notes

The `slack_screenshots/` baseline highlighted recurring anti-patterns:

- Parent message too verbose before any actionable content.
- TL;DR list expanded into near-full report.
- Over-reliance on low-emphasis context rows.
- Inconsistent readability under dark mode.

Regression prevention:

- Maintain snapshot fixtures in `tests/fixtures/slack/`.
- Keep at least one regression fixture representing prior wall-of-text failures.
- Validate both payload shape and readability contracts in tests.

## Accessibility Rules

- Include meaningful top-level `text` fallback on every post.
- Do not rely on color alone for state; include textual badges.
- Provide `alt_text` for image accessories.
- Provide `accessibility_label` for interactive buttons.
- Keep context lines concise for screen-reader scanability.

## Validation Checklist

Before shipping Slack renderer changes:

1. `pytest -q` passes.
2. Slack rendering contract tests pass.
3. Snapshot fixtures updated intentionally (no accidental churn).
4. Overflow/action payloads verified against Slack limits.
5. No secrets in logs, fixtures, snapshots, or docs.
