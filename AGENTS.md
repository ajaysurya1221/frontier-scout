# AGENTS Guide

Frontier Scout: **sanctioned MCP-server packs for coding assistants (Claude Code
first)** — repo-rank approved MCP servers into a **static** capability + policy safety
map, then **export a Claude Code managed-config fragment** an admin deploys. Local,
keyless, offline by default; a **research preview** (technically coherent, **not**
market-validated). The repo-aware **adoption radar** that powers ranking and the TUI is
the engine underneath the packs product. Use this file as the handoff playbook for
humans and coding agents landing on the repo.

## Repo layout

```text
frontier_scout/        # installable CLI package
  cli.py               # entry point + --ui/--provider/--demo. Subcommands include:
                       #   packs (candidates/sanction/unsanction/export/proof/list/show/refresh),
                       #   scan report evaluate dossier lab trial guard policy deps profile stats,
                       #   incident (PARKED, experimental)

  # --- the sanctioned-packs product (the headline) ---
  packs.py             # pack model, candidate discovery, registry parse, repo-ranked rows
  pack_flow.py         # candidates -> static safety -> risk-gated sanction -> export orchestration
  safety_summary.py    # STATIC capability + policy safety map (no MCP server executed)
  proof_variants.py    # A/B/C proof variants (approval-only / static-summary / receipt)
  exporters/
    claude_config.py   # Claude Code managed allowedMcpServers/deniedMcpServers + project .mcp.json
  telemetry.py         # local opt-in pack funnel (`frontier-scout stats`)

  # --- the radar engine underneath ---
  scout.py             # stack detection + CLI-facing scan wrapper
  evaluate.py dossier.py lab.py trials.py   # eval / dossier / lab / trial receipts
  policy.py mcp_audit.py guard.py           # Adoption Firewall: policy, MCP perm classifier, guard
  profile.py           # local Scout Profile for repo-aware recommendations
  report.py            # static HTML/Markdown report renderer + demo fixtures
  store.py             # local SQLite store under ~/.frontier-scout (packs, adoption_decisions)
  dependencies.py dep_trial.py imports.py   # dependency intel + AST import names

  # --- the agent adoption firewall (static, advisory; research preview) ---
  agent_firewall/      # scan repo risk surfaces, conservative policy, task check, JSON receipts
    models.py scan.py policy.py decision.py receipts.py
  exporters/policy_snippets.py   # advisory CLAUDE.md / AGENTS.md / PR-checklist snippet exporters

  tui3/                # Mission Control TUI (Textual) — the DEFAULT `frontier-scout` UX
  tui2/  tui/          # alternative UIs: --ui briefing (tui2) / --ui classic (tui)
  providers/           # LLM provider abstraction: anthropic / openai / claude-cli / codex-cli
  platform/incident_change_scout/   # PARKED experimental vertical (FRONTIER_SCOUT_EXPERIMENTAL=1)

scripts/               # mature engine modules (fetch -> score -> verdict -> judge -> validate; lab_runner; ...)
outputs/               # shared rendering helpers
tests/                 # non-live regression tests
demo/                  # generated public demo artifacts
docs/                  # docs/pivot (decisions) · docs/examples/sanctioned-packs (gold path) · docs/assets (SVGs)
examples/  prompts/  evals/incident_change_scout/   # fixtures for the PARKED incident vertical only
```

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# the sanctioned-packs product (keyless, offline)
frontier-scout packs candidates --repo . --client claude-code
frontier-scout packs sanction <server> --repo .        # high-risk needs --acknowledge-risk
frontier-scout packs export --client claude-code --target ./out

# the agent adoption firewall (static, advisory; keyless, offline)
frontier-scout agent scan                       # repo risk surfaces (secrets by name only)
frontier-scout agent policy init                # -> conservative frontier-scout.policy.json
frontier-scout agent check "upgrade requests and run the tests"   # -> allow/needs_approval/block
frontier-scout agent receipts list              # local audit trail (.frontier-scout/receipts/)

# the radar engine underneath
frontier-scout                 # opens Mission Control TUI (default); --ui briefing|classic, --demo offline
frontier-scout demo
frontier-scout scan --dry-run --repo .
frontier-scout guard --repo .
```

Live radar scans need `ANTHROPIC_API_KEY` (the sanctioned-pack flow does not).
`GITHUB_TOKEN` is optional and only raises GitHub REST rate limits.

## Test commands

- Full non-live suite: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
  (local conda: `/opt/miniconda3/bin/python`; the 3 `tests/test_implement.py` fails are env-only).
- Sanctioned packs: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_packs_*.py tests/test_pack_*.py tests/test_safety_summary.py tests/test_sanction_gating.py tests/test_exporters_*.py`
- Adoption Firewall: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_policy.py tests/test_mcp_audit.py tests/test_trials.py tests/test_guard.py`
- Agent firewall (the `agent` group): `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_agent_*.py`
- Personalized Scout: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_profile_dossier.py`
- tui3 convergence (golden-frame + cell-width gates): `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -k "tui3 and (golden or cells or bridging)"`. The `pytest-textual-snapshot` SVG snapshots are **local-only** (add `-p pytest_textual_snapshot`); CI skips them via `tests/conftest.py`.
- Syntax sweep: `python -m compileall scripts outputs tests frontier_scout`
- Demo smoke: `frontier-scout demo`

## Conventions

- **Sanctioned packs are static + Claude-Code-first + research-preview.** The pack flow
  **never executes** an MCP server (static capability + policy map only); exporters
  **emit** config, they do **not enforce** runtime policy; Copilot / Cursor / Docker are
  **roadmap**, not built. Make no PMF / adoption / market-validation claim in copy.
- **CLI/report first.** Do not make plugin setup the first-run requirement.
- **Local state stays local.** Runtime files belong in `~/.frontier-scout` or ignored scratch directories.
- **Verdict schema is load-bearing.** `category`, `risk`, `fit`, `readiness`, and `source_url` must stay aligned across prompts, tools, validators, reports, the safety summary, candidates `--json`, exporters, and tests.
- **All LLM calls go through the provider abstraction** (`frontier_scout/providers/`): pin one backend with `--provider anthropic|openai|claude-cli|codex-cli`. Needs exactly one; `--demo`/offline and the pack flow need none. Availability **deep-probes** `<cli> --version` (cached) so a broken-but-on-PATH CLI is skipped, not silently selected; the hermetic claude scout passes `--mcp-config '{"mcpServers": {}}'` (claude 2.x rejects a bare `"{}"`).
- **tui3 glyph-art is cell-precise.** The Adoption Matrix (59-cell box-grid), gauges/`meter`, and the scan `sweep`/spinner are width-parameterized pure functions (`fn(width)->str`); measure width with `kit.cell_width` (Rich `cell_len`), **never `len()`** (multi-cell ASCII `(o)`=3, `->`=2 drift); build per-mode (`unicode=state.unicode`); converge on `design_handoff_mission_control_v6/ascii_golden_frames.txt`. Every renderable still routes through `app._paint` + `glyphs()`.
- **Lab subprocesses must stay hermetic.** Reuse `_hermetic_base_env()`; never pass `os.environ` into untrusted package code.
- **Do not auto-install recommendations.** The lab tests; the user chooses.
- **Adoption Firewall is evidence, not autonomy.** `evaluate`, `trial`, `guard`, and
  `sanction` record local receipts and policy findings; they must not silently grant
  repo, shell, browser, network, or credential permissions.
- **Scout Profile is metadata, not code upload.** Profile/dossier/ranking features use
  manifests, config filenames, local history, and policy signals; do not read
  `.env.local` or upload source content for personalization.
- **`incident` (Incident Change Scout) is parked.** A separate experimental vertical
  behind `FRONTIER_SCOUT_EXPERIMENTAL=1`; keep the code, don't surface or extend it as
  part of the packs product.
- **The agent adoption firewall (`agent` group) is static + advisory.** `agent scan` / `check`
  **execute nothing** (no subprocess/network/LLM — the only subprocess is a guarded read-only
  `git rev-parse` for receipt metadata); secret-likely files are matched **by name/path only**
  (contents never read); exporters and snippets **emit**, they do **not enforce**; the policy loader
  and decision engine **fail closed** (a missing/malformed `frontier-scout.policy.json` denies by
  default). The non-executing task check is `agent check`, **never** `trial`. It reuses the existing
  risk taxonomy (`mcp_audit`, `RISKY_FLAGS`, `PolicyFinding`) and redacts every emitted/persisted
  string via `outputs/_text.scrub_secrets`.

## Working principles

General discipline for any change here — adapted from the
[Karpathy coding guidelines](https://github.com/multica-ai/andrej-karpathy-skills) (MIT).
**Conventions** above are repo-specific invariants; these are the *how you work* rules.

- **Think before coding.** Surface your assumptions and name the interpretations you
  weighed before editing; when a request is ambiguous or looks wrong, push back instead
  of guessing. (Changes that need a discussion first are under **Ask before changing**.)
- **Simplicity first.** Write the minimum that satisfies the task — no speculative
  abstractions, flags, or "while I'm here" extras. YAGNI.
- **Surgical changes.** Touch only what the task requires and match surrounding style;
  keep diffs reviewable and leave unrelated code alone.
- **Goal-driven execution.** Define verifiable success criteria up front, then loop until
  they pass — here that means the **Definition of done** below.

## Definition of done

1. `python -m compileall scripts outputs tests frontier_scout` passes.
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` passes.
3. `frontier-scout demo` regenerates clean demo artifacts.
4. README, ROADMAP, SECURITY, CONTRIBUTING, **CLAUDE.md, and AGENTS.md** match any
   user-visible behavior or identity change.
5. No secrets or noisy runtime ledgers are introduced in git diff.

## Release

1. Bump `version` in `pyproject.toml` + `frontier_scout/__init__.py`; add a `CHANGELOG.md` entry.
2. PR → CI `test` (full suite + `detect-secrets --all-files` secret scan + CodeQL).
3. `main` is protected (1 review + `enforce_admins` + conversation-resolution, **squash-only**);
   merge via the relax→merge→restore dance on `required_approving_review_count` (1→0→1; always
   restore), squashing with `gh pr merge --squash --admin`.
4. Tag `vX.Y.Z` → `release.yml` publishes the GitHub Release (draft→publish) + PyPI
   (trusted publishing, gated by the `pypi` deployment environment — approve the run).
5. Non-`.py` data (`tui3/theme.tcss`) must be in `[tool.setuptools.package-data]` + `MANIFEST.in`,
   or the installed TUI crashes on launch — verify the **built wheel** bundles the `.tcss`.
6. Never reuse a burned version: GitHub immutable-releases permanently reserve a deleted tag
   name (`v1.5.0` is dead); bump to the next patch.

## Ask before changing

Open an issue or discuss first before adding:

- a new source group or quota,
- a new lab runtime,
- a new LLM vendor,
- a new export client (Copilot / Cursor / Docker / GitHub) — currently roadmap,
- a hosted service or sync feature,
- an auto-install path for recommended tools.
