# AGENTS Guide

This repo is Frontier Scout — an AI-tooling radar that lives inside
Claude Code. Use this file as the handoff playbook for humans and coding
agents landing on the repo.

## Repo layout (v0.1, in progress)

```
scripts/      # the engine — independent of any UI surface
  scout.py        # run_scan() — fetch → score → verdict → judge → validate
  lab_runner.py   # polyglot lab dispatcher (Python / Node / HuggingFace)
  judge.py        # Opus RLAIF pass (gated by JUDGE_ENABLED)
  validators.py   # Pydantic policy gates — URL allowlist, anti-injection,
                  # incident-as-tool veto, ADOPT-requires-readiness demote
  prompts.py      # stack-parameterised system prompts (no hardcoded stack)
  tools.py        # Anthropic tool-use JSON schemas
  cost_tracker.py # append-only costs.jsonl ledger
  quality_logger.py # append-only quality-log.jsonl ledger
  demo.py         # SAMPLE_VERDICTS + offline HTML preview
  llm_client.py   # retry wrapper around the Anthropic SDK

outputs/      # how verdicts are rendered (engine-agnostic)
  _text.py        # shared clip / escape / sanitize helpers
  __init__.py     # plug-in conventions

tests/        # focused, fast, no live LLM calls (those are marked `live`)
  test_lab.py
  test_validators.py

# coming in Phase 3+ (not yet in the repo):
# fs_cli/   — CLI + SQLite + scheduler + first-run wizard
# fs_mcp/   — FastMCP server (the Claude Code surface)
# skill/    — Claude Code skill bundle that installs under ~/.claude/skills/
# pyproject.toml — entry points + dependencies
# .github/workflows/test.yml — CI
```

## Local run (what works today)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) Offline preview (no API keys, no network):
python scripts/demo.py && open demo/briefing.html

# 2) Live scan to stdout (needs ANTHROPIC_API_KEY):
ANTHROPIC_API_KEY=… python scripts/scout.py

# 3) Tests (no live LLM):
pytest -q
```

`fs_cli`-driven `frontier-scout init / scan / latest / lab` lands in
Phase 3. Until then there's no install story.

## Test commands

- Full non-live suite: `pytest -q`
- Lab regressions only: `pytest -q tests/test_lab.py`
- Validator gates only: `pytest -q tests/test_validators.py`
- Syntax sweep: `python -m compileall scripts outputs tests`

## Conventions

- **Verdict schema is load-bearing.** `risk` (low/medium/high) and `fit`
  (high/medium/low against `stack.yaml`) replaced the legacy `soc2` field.
  Both Anthropic tool schemas (`scripts/tools.py`) and the Pydantic
  validator (`scripts/validators.py`) enforce this — touch one, touch the
  other.
- **Hermetic env for any subprocess that runs untrusted code.** Reuse
  `lab_runner._hermetic_base_env()`; never pass `os.environ` directly.
  Backed by `tests/test_lab.py::TestLabRuntimeDispatch::test_hermetic_base_env_has_no_secrets`.
- **No hardcoded stack.** Prompts are parameterised on the user's
  `stack.yaml` (built by `fs_cli.stack_detect` in Phase 3). The engine
  works with `stack_profile=None` — it just frames verdicts on universal
  merit.
- **All Anthropic calls go through `llm_client.call_with_retry`.** That
  wrapper provides exponential backoff + structured stats for
  `quality-log.jsonl`.
- **Storage is local-only.** No central service, no auth, no hosted
  sync. The MCP server (Phase 5) reads SQLite at
  `~/.frontier-scout/db.sqlite`; the scheduled scan (Phase 3) writes it.

## Definition of done

A change is done only when all are true:

1. `pytest -q` passes locally.
2. `python -m compileall scripts outputs tests` succeeds.
3. README + ROADMAP reflect any user-visible behaviour change in the
   same commit.
4. No secrets are introduced in the git diff (`detect-secrets scan`
   stays clean once Phase 7's CI workflow lands).
5. New subprocess paths use `lab_runner._hermetic_base_env()` and a
   wall-clock timeout.

## Where to file an issue first

Open one before adding:
- a new source feed (the funnel's quotas + dedupe + seen-filter
  have non-obvious invariants),
- a new lab runtime (the safety model has to match the three
  existing runtimes),
- a new MCP tool (the public surface is small on purpose — every
  added tool is a maintenance commitment).
