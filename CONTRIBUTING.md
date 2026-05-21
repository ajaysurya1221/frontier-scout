# Contributing

PRs welcome. Keep them small and focused.

## Local dev setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pre-commit detect-secrets
pre-commit install
cp .env.example .env  # fill in real values
```

## Before opening a PR

```bash
# Unit tests — zero API cost
pytest tests/test_validators.py tests/test_pipeline_bits.py tests/test_lambda_handler.py -v

# Live tests — ~$0.05, requires ANTHROPIC_API_KEY
pytest tests/ -m live -v

# Lint + secret scan
pre-commit run --all-files

# Try the pipeline locally without sending anywhere
DRY_RUN=1 python scripts/scout.py
```

## What kinds of PRs land fast

- **Source additions**: new RSS feeds, GitHub repos, or a new fetcher in `scripts/scout.py`. Include a one-line rationale.
- **Validator rules**: tightening `scripts/validators.py` policy gates with a regression test.
- **Prompt updates**: surgical edits to `scripts/prompts.py`. Bear in mind every change invalidates the Anthropic prompt cache once.
- **Slack format**: refinements to `scripts/slack_post.py`. Include a `DRY_RUN=1` payload snippet in the PR description.

## What gets pushback

- Adding agent frameworks (CrewAI, LangGraph) to the scheduled pipelines. Linear Python is the architectural choice for determinism + bounded cost.
- New LLM vendors. Anthropic + OpenAI (embeddings only) is the SOC2 vendor surface.
- Adding chrome to the Slack message without a clear use case.
- Anything that bypasses the policy-gate layer in `scripts/validators.py`.

## Architecture sketch

```
fetch → dedupe → Mem0 prior-filter → stratified cap
  → Sonnet score → Sonnet verdicts → Opus judge → validators → Slack
```

Every Anthropic call routes through `scripts/llm_client.py` with retry +
backoff. Every pipeline writes a row to `quality-log.jsonl`. See
`README.md`, `SECURITY.md`, and `ROADMAP.md` for the full picture.

## Reporting security issues

Don't file a public issue. Email the repo owner directly.
