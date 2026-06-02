# CLAUDE.md — Frontier Scout

**Read `AGENTS.md` first — it is this repo's full handoff playbook** (repo layout,
local run, test commands, conventions, definition of done, "ask before changing").
This file is the Claude Code quick-load companion: the current facts an agent needs
before touching the code.

## What this is

Frontier Scout — a local **AI adoption radar** (CLI + Textual TUI) for tools, MCP
servers, agent frameworks, and model drops. Python 3.11+, packaged with setuptools,
shipped to GitHub Releases + PyPI.

## The default UX is the TUI

Bare `frontier-scout` opens **Mission Control** (`frontier_scout/tui3/`, Textual) —
a dense, keyboard- **and** mouse-driven, 8-tab dashboard
(Scout · Schedule · Receipts · Guard · Packs · Deps · Reports · Settings).

- `--ui {mission,briefing,classic}` selects the UI (`mission` = tui3 default,
  `briefing` = tui2, `classic` = tui); `--demo` runs fully offline.
- Every renderable goes through `app._paint` (color↔mono) and `glyphs(unicode)`
  (unicode↔ASCII); layout reflows by breakpoint (`kit.breakpoint_for`). New
  widgets must route through these, or the fallbacks break.
- Lists that refresh use a single id-tagged `Static` repainted via `.update()`
  (never `remove_children()` + remount with the same ids → DuplicateIds).

## LLM backends (provider abstraction)

Needs **exactly one** backend; `--demo`/offline needs none. Pin with
`--provider anthropic | openai | claude-cli | codex-cli` (`frontier_scout/providers/`).
(This supersedes the older "all calls via `scripts/llm_client.py`" note.)

## Tests in this environment

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

- In the local conda setup use `/opt/miniconda3/bin/python` (bare `python` may not
  be on PATH). The 3 `tests/test_implement.py` failures are **env-only** (they shell
  out to `python`) — ignore them locally; they pass on CI.
- Some tui3 tests (`test_pressing_s/r`, the cap-scan click tests) run the **real**
  demo scan, which is slow on a cluttered local tree (~10–15s), so they can time out
  locally yet pass on a clean CI checkout. Isolate a suspected regression by stashing
  and comparing against a clean tree before assuming you broke it.

## Packaging gotcha (load-bearing)

Non-`.py` data files (the Textual `theme.tcss` stylesheets) MUST be declared in
`pyproject.toml` `[tool.setuptools.package-data]` (`"*" = ["*.tcss"]`) + `MANIFEST.in`,
or `pip install` ships a wheel that **crashes on launch** (`StylesheetError`). Verify
a release against the **built wheel** (it bundles `tui3/theme.tcss` + `tui3/widgets.py`),
never the source tree. `release.yml` has a guard that fails the build if the wheel
lacks the stylesheets.

## Release process

1. Bump `version` in `pyproject.toml` + `frontier_scout/__init__.py`; add a
   `CHANGELOG.md` entry.
2. PR → CI `test` (full suite + `detect-secrets --all-files` secret scan + CodeQL).
   The secret scan flags keyword literals like `"credential"`/`"secrets": "..."`;
   mark genuine false positives with `# pragma: allowlist secret`.
3. `main` is protected (1 review + `enforce_admins`, **squash-only**): merge via the
   relax→merge→restore dance — PATCH `required_approving_review_count` 1→0, squash,
   then →1 (always restore).
4. Tag `vX.Y.Z` → `release.yml` publishes the GitHub Release (draft→publish,
   immutable-safe) + PyPI (trusted publishing, gated by the `pypi` deployment
   environment — approve the pending deployment via `gh api ... pending_deployments`).
5. Verify the GitHub assets **and** the PyPI wheel bundle the `.tcss` stylesheets.
6. **Never reuse a burned version:** GitHub immutable-releases permanently reserve a
   deleted release's tag name (`v1.5.0` is dead) — bump to the next patch instead.

## Security / conventions

See `AGENTS.md` → "Conventions" and "Ask before changing". Load-bearing invariants:
repo source is never sent to an LLM (only filenames + AST import names); fetched
release text is data, not instructions; lab subprocesses stay hermetic; nothing
auto-installs; `evaluate`/`trial`/`guard` record evidence and never grant repo/shell/
network/credential permissions; don't read `.env.local` or upload source for
personalization.
