# AGENTS Guide

This repo powers Frontier Scout's weekly/daily/monthly pipeline and Slack delivery surfaces.
Use this file as the handoff playbook for humans and coding agents.

## Repo Layout

- `scripts/scout.py`: Weekly pipeline (fetch -> score -> verdict -> judge -> validate -> Slack + artifacts).
- `scripts/pulse.py`: Daily Tier-S pipeline.
- `scripts/synthesizer.py`: Monthly synthesis pipeline.
- `scripts/slack_post.py`: Slack rendering + delivery helpers (primary Block Kit surface).
- `scripts/evaluate_from_slack.py`: Deep-eval thread reply path from Slack button action.
- `scripts/tools.py`: Structured-output schemas for LLM tool calls.
- `scripts/validators.py`: Deterministic post-LLM policy gates.
- `lambda/`: Slack interaction handlers (`/radar`, `/recall`, button dispatch).
- `tests/`: Unit/regression tests, including Slack rendering contracts and fixtures.
- `tests/fixtures/slack/`: Snapshot fixtures for polished Slack payloads and regression inputs.

## Local Run

- Setup:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Dry-run render paths:
  - `DRY_RUN=1 python scripts/scout.py`
  - `DRY_RUN=1 python scripts/pulse.py`
- Demo UI (no external services):
  - `python scripts/demo.py`

## Test Commands

- Full suite: `pytest -q`
- Slack-focused: `pytest -q tests/test_pipeline_bits.py tests/test_slack_rendering_contracts.py tests/test_evaluate_from_slack_rendering.py`
- Syntax check: `python -m compileall scripts lambda tests`

## Slack Rendering Conventions

- Slack copy must answer three questions quickly: what happened, why it matters, what to do next.
- Use deterministic Block Kit rendering from structured fields; avoid freeform long prose in top-level summaries.
- Keep key information in `section` blocks (not only `context`), and reserve `context` for secondary metadata.
- Every post must include descriptive top-level fallback `text`.
- Do not rely on color alone for tier state; include textual tier labels.
- Overflow option values must stay under Slack limits and must not include unsupported keys (e.g. `confirm` in overflow options).

## Secrets and Safety Rules

- Never print or commit `.env` values.
- Never log raw Slack webhook/action URLs or tokens.
- Redact secret-like strings in error logs and dead-letter records.
- Keep fixtures synthetic; no production channel data or tokens.
- Do not post test messages to production channels unless intentionally configured.

## Definition of Done

A change is done only when all are true:

1. Slack payloads are valid and render cleanly (threaded + webhook paths).
2. Screenshot-class regressions are covered by tests/fixtures.
3. `pytest -q` passes locally.
4. No secrets or noisy generated telemetry files are introduced in git diff.
5. Docs are updated when rendering architecture or conventions change.
