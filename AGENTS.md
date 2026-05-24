# AGENTS Guide

This repo is Frontier Scout: a local AI adoption radar for tools, MCP servers,
agent frameworks, and model drops. Use this file as the handoff playbook for
humans and coding agents landing on the repo.

## Repo layout

```text
frontier_scout/     # installable CLI package
  cli.py            # argparse entry point: init, demo, scan, report, lab
  scout.py          # stack detection + CLI-facing scan wrapper
  report.py         # static HTML/Markdown report renderer + demo fixtures
  store.py          # local SQLite store under ~/.frontier-scout
  lab.py            # wrapper around scripts/lab_runner.py

scripts/            # mature engine modules
  scout.py          # fetch -> score -> verdict -> judge -> validate
  lab_runner.py     # polyglot lab dispatcher (Python / Node / Hugging Face)
  judge.py          # optional Opus judge pass
  validators.py     # deterministic policy gates
  prompts.py        # stack-parameterized system prompts
  tools.py          # Anthropic tool-use JSON schemas

outputs/            # shared rendering helpers
tests/              # non-live regression tests
demo/               # generated public demo artifacts
```

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

frontier-scout demo
frontier-scout init --repo .
frontier-scout scan --dry-run --repo .
```

Live scans need `ANTHROPIC_API_KEY`. `GITHUB_TOKEN` is optional and only raises
GitHub REST rate limits.

## Test commands

- Full non-live suite: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
- Lab regressions: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_lab.py`
- Validator gates: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_validators.py`
- Syntax sweep: `python -m compileall scripts outputs tests frontier_scout`
- Demo smoke: `frontier-scout demo`

## Conventions

- **CLI/report first.** Do not make plugin setup the first-run requirement.
- **Local state stays local.** Runtime files belong in `~/.frontier-scout` or ignored scratch directories.
- **Verdict schema is load-bearing.** `category`, `risk`, `fit`, `readiness`, and `source_url` must stay aligned across prompts, tools, validators, reports, and tests.
- **All Anthropic calls go through `scripts/llm_client.py`.**
- **Lab subprocesses must stay hermetic.** Reuse `_hermetic_base_env()`; never pass `os.environ` into untrusted package code.
- **Do not auto-install recommendations.** The lab tests; the user chooses.

## Definition of done

1. `python -m compileall scripts outputs tests frontier_scout` passes.
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` passes.
3. `frontier-scout demo` regenerates clean demo artifacts.
4. README, ROADMAP, SECURITY, and CONTRIBUTING match any user-visible behavior.
5. No secrets or noisy runtime ledgers are introduced in git diff.

## Ask before changing

Open an issue or discuss first before adding:

- a new source group or quota,
- a new lab runtime,
- a new LLM vendor,
- a hosted service or sync feature,
- an auto-install path for recommended tools.
