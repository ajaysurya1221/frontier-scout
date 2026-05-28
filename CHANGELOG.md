# Changelog

## Unreleased

### Demo UX (lands in 1.2.2)

- `frontier-scout demo` now starts a localhost HTTP server by default
  and opens the briefing in the browser. Use `--no-serve` for CI /
  offline / file-only runs.
- The demo briefing page links the companion artifacts:
  `briefing.md`, `verdicts.json`, `cost-breakdown.md`,
  `judge-trace.md`, `quality-log.jsonl`. The artifact nav only renders
  when those files exist (CLI `report` flow doesn't show dead links).
- Server binds to `127.0.0.1` by default; widens to `0.0.0.0` only
  when `_is_remote_env()` detects VS Code Server / Codespaces / a
  devcontainer with port forwarding. The handler enforces a path
  allowlist so other files in the output dir never leak.
- README adds the `frontier-scout demo` walkthrough.
- Tests: artifact-link presence, root → briefing routing, demo-server
  readiness retry (race-free), allowlist guard.

## 1.2.0 - 2026-05-28

The honest fix. v1.1 accreted too many features; in real use the
splash lied about "press any key", action buttons returned *"No
verdict highlighted"*, the detail panel froze on *"Scouting…"*, Deps
showed `—` for every reason, Incident crashed on missing paths, and
Reports only ever rendered the demo. v1.2 strips the TUI to two tabs,
fixes every defect, and surfaces the *why* behind every recommendation
so a college intern can drive it without help.

### What's gone from the TUI

The CLI keeps everything; only the TUI shape changes.

- **Splash deleted.** No more "press any key — auto-continue" lie. Cold
  launch drops from ~5s to <1s.
- **Welcome modal deleted.** First-run friction removed.
- **Incident tab deleted** (demo, not a user workflow). CLI:
  `frontier-scout incident demo`.
- **Packs tab deleted** (internal concept). CLI: `frontier-scout packs
  list/show/refresh`.
- **Trials tab deleted** (folded into Scout's per-row action). CLI:
  `frontier-scout trial …`.
- **Receipts tab deleted** (read via CLI / SQLite). CLI: see
  `frontier-scout dossier`.
- **Reports tab deleted** (one clickable link in the brand bar opens
  the auto-generated report). CLI: `frontier-scout report`.
- **Guard tab deleted** (folded into Scout as a banner when findings
  need attention). CLI: `frontier-scout guard`.
- **Deps tab deleted** (folded into Scout — dependency upgrades appear
  in the same verdict list as AI tools). CLI: `frontier-scout deps
  scan`.
- **"Evaluate URL" button + Input deleted** — every verdict already
  carries `source_url`, so asking the user to paste was friction for
  nothing. CLI: `frontier-scout evaluate <url>` for ad-hoc URLs.

### Defects closed

- **"No verdict highlighted" on every action.** The DataTable cursor
  now auto-positions to row 0 the moment verdicts load, and buttons
  fall back to row 0 if no cursor is set.
- **Detail panel stuck on "Scouting…".** The first verdict's full
  reasoning renders automatically when the scout completes.
- **Strike-throughs in the verdict list.** Dismissed verdicts are
  filtered out cleanly. `[c]` clears history + dismissals so the user
  always sees a fresh state.
- **Deps Why / Severity always "—".** The Deps renderer was reading
  fields that don't exist on `DependencyFinding`. Now it renders the
  real fields: classification, classifier_confidence, evidence quotes
  joined as the "why", verdict, repo_fit, advisory IDs, next safe step.
- **Incident `FileNotFoundError`.** The tab is gone. CLI runs from the
  source repo as before.
- **Reports only showed demo.** Auto-scout now uses `persist=True`,
  the brand bar's `📊 report` link renders a real HTML report for this
  repo. Press `r` from anywhere in the TUI to open it.
- **Settings handlers crashing the tab.** Every renderer and handler
  is wrapped in try/except; broken filesystems show
  `[rendering error: …]` inline instead of crashing.
- **5–6s cold launch.** Splash gone (saves 1.4s) and the import scan
  is deferred until the Scout tab's worker fires after mount. Cold
  launch now ~0.8s in plain mode.
- **Repo picker not firing on Desktop.** Splash gone → picker mounts
  reliably when `not looks_like_repo(repo)`.

### What the Scout tab does now

One unified list of findings drawn from two engines:

- AI-tool verdicts (ADOPT / TRIAL / ASSESS / HOLD) from `run_scan`.
- Dependency upgrade findings from `run_dependency_scan`.

Both render in the same `DataTable` with `category` column showing
their source (`mcp_server`, `dependency:security`, etc.). A top-of-tab
toggle `[× AI tools] [× Dependencies]` controls scope (persisted to
`setup_state.json`). A guard banner appears inline above the table
when any tool needs a sandbox receipt — with the *why* and a one-press
`Try locally` to write it.

The detail panel default-populates with the first verdict's full
reasoning: **What** · **Why we suggest this** · **Why it fits your
repo** (the personalised `fit_reasons`, finally surfaced) · **Risk
reasoning** · **Next safe step** · **Source URL**.

Three actions: `[Try locally]` (Enter), `[Open URL]`, `[Dismiss]`.

### Keymap

```
↑ ↓        choose a finding
Enter      Try locally (writes a dry-run receipt)
s          rescout
c          clear scout memory + dismissals for this repo
r          open scout HTML report
/          change repo path
?          help
1 / 2      Scout / Settings
q          quit
```

### Tests

172 passing (down from 179 because tests for deleted tabs were
removed). All new tests verify the fixed defects: auto-cursor on
load, detail panel populated, settings panels never crash, etc.

### CLI changes

None — every removed TUI surface still has its CLI command. New
runtime dep from v1.1 (`croniter`) stays.

## 1.1.0 - 2026-05-27

The head-turner release. `frontier-scout setup` becomes a global config
wizard; the TUI gets a repo-picker fallback, notifications, diff-view,
and clear-memory; tree-sitter coverage extends to Go / Rust / Ruby; and
a `doctor` command lets every install self-check.

- **Setup wizard** — `frontier-scout setup` (run from anywhere) walks
  through Welcome → LLM backend (auto-detected with copy-friendly setup
  commands; **keys never written to disk by us**) → Mode (Automation /
  Ad-hoc) → either schedule configuration with a one-line crontab the
  user adds once, or a how-to screen for ad-hoc users. Headless mode
  via `frontier-scout setup --automation --repo PATH --cron '@daily'`.
- **Automation + cron scheduling** — `~/.frontier-scout/schedules.json`
  describes recurring scouts; the wizard installs
  `~/.frontier-scout/cron-runner.sh` and surfaces the single crontab
  line. `frontier-scout cron run` is the headless executor invoked by
  the runner.
- **Notifications** — when a scheduled scout finds new ADOPT/TRIAL
  verdicts versus the prior scan for that repo, a JSON notification
  lands under `~/.frontier-scout/notifications/`. Optional system
  notification via `terminal-notifier` (macOS) or `notify-send`
  (Linux). Brand bar surfaces an `(N new)` chip; `Ctrl-N` opens a
  modal listing them. CLI sibling: `frontier-scout notifications [list|clear]`.
- **Repo picker fallback** — running `frontier-scout` outside a repo
  no longer scans an empty cwd. A modal opens listing `$PWD`,
  `$HOME`, and recent repos; pick one to begin.
- **Diff view (`d`)** — compare the current scout against the previous
  persisted scan for the same repo. Modal shows New / Changed /
  Retired verdicts with verdict + fit + risk shifts.
- **Clear scout memory** — Scout tab `[c]` and a Memory panel in
  Settings clear stored scan history for the current repo (or all
  repos). CLI sibling: `frontier-scout clear-history [--repo PATH | --all]`.
- **Tree-sitter Go / Rust / Ruby** — `ImportEvidence` gains `go_imports`,
  `rust_imports`, `ruby_imports`. Curated stdlib filters drop the
  noise. New `_GO_*_RULES`, `_RUST_*_RULES`, `_RUBY_*_RULES` rule
  tables in `profile.py` map common AI / agent / framework packages
  to the same fingerprint tags Python and JS already populate.
  `Cargo.lock`, `go.sum`, `Gemfile.lock` added to the manifest walker.
- **`frontier-scout doctor`** — self-diagnostics covering Python /
  Textual / tree-sitter / home dir / SQLite / schedules / cron-runner
  / optional CLIs / system notifier. JSON output via `--doctor --json`.
- **Settings tab gains Memory + Automation panels** — see schedules,
  the crontab line, and clear-memory buttons without leaving the TUI.
- **New CLI subcommands** — `open` (explicit TUI launcher), `cron run`
  (schedule executor), `doctor`, `clear-history`, `notifications`.
  `setup --wizard` forces the wizard even if other flags would route
  to the TUI; bare `setup` without flags lands on the wizard, while
  `setup --repo .` / `--plain` / `--json` keep their v1.0 behavior.
- **Hero SVG fixed** — radar bottom no longer overlaps the safety
  footer (was a real defect); version label updated to `v1.1`;
  bottom badge row moved inside the terminal frame for cleaner
  composition; alt text + `<title>` updated to the v1.0 tagline.
- **README narrative refresh** — leads with the selling lines:
  *"Deep Scout — know before everyone else"*, *"Try before trust"*,
  *"Fix vulnerabilities you didn't know existed"*, *"Bound risky
  engineering changes"*. Quickstart now leads with the wizard.
- **Croniter** added as a runtime dependency (≥2.0, MIT) for cron
  expression parsing. Falls back to macro-only mode if absent.
- **Tests**: 179 passing (up from 148). New `tests/test_scheduling.py`,
  `tests/test_notifications.py`, `tests/test_doctor.py`,
  `tests/test_wizard.py`, `tests/test_imports_multilang.py`,
  `tests/test_clear_memory.py`.
- **Ruff** clean on every new module.

## 1.0.0 - 2026-05-27

The "everything in the TUI" release. Mission Control v3 is a tabbed,
scout-first workspace; every CLI capability now has a TUI surface.

- **Tabbed Mission Control.** Nine tabs (`Scout`, `Trials`, `Receipts`,
  `Guard`, `Reports`, `Packs`, `Deps`, `Incident`, `Settings`) on a
  Textual `TabbedContent`. `1`–`9` jump by number, `Tab`/`Shift-Tab`
  cycles widgets, the active tab gets a mint accent.
- **Scout tab (the strongest pitch — default landing).** Auto-runs a
  dry-run scout on mount in a background worker (~0.2s, local, free)
  and renders the resulting ADOPT / TRIAL / ASSESS / HOLD verdicts in a
  color-coded `DataTable`. `[Trial dry-run]`, `[Evaluate]`, `[Dossier]`,
  `[Open URL]`, `[Dismiss]` act on the highlighted row. `s` rescouts,
  `l` runs a live scout (gated on `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
  presence, double-press to confirm spend), `/` filters by substring.
  Dismissed tools persist to `setup_state.json["dismissed_tools"]`.
- **Trials tab** — stored trial history + `[+ New Trial]` form that
  calls `run_trial(..., dry_run=True)`.
- **Receipts tab** — master/detail read-only view over the local
  evidence ledger (trial runs + decisions + receipt paths).
- **Guard tab** — `[Run guard]` with `[Strict]` toggle, color-tinted
  severity column, CI-style summary line.
- **Reports tab** — `[Generate offline demo]` / `[Render latest scan]` /
  `[Open most recent]` buttons; recent reports persisted to
  `setup_state.json["recent_reports"]`.
- **Packs tab** — pack list, per-pack detail + candidates,
  `[Refresh seeds]` and `[Refresh + discover]` (network gated by
  double-press confirmation).
- **Deps tab** — `[Run scan]` → findings table → per-finding
  `[Create trial]` writes a `run_dependency_trial` receipt.
- **Incident tab** — `[Run incident demo]` with `[Approved]` toggle,
  four artifact paths and `[Open answer]` / `[Open trace]` /
  `[Open eval]` buttons.
- **Settings tab** — three panels: Policy (init to home or repo;
  current file preview), Environment (env-var presence only, values
  never read), System (version, home, `setup_state.json` JSON,
  `[Reset setup state]`).
- **Brand language**: tagline updated to *"the radar for latest AI
  releases that fit your repo."* Brand bar, splash, and README hero
  all carry the same line.
- **CLI**: new flags `--tab NAME` (land directly on a specific tab) and
  `--no-scout` (skip the auto-scout for a faster TUI launch). `--plain`
  output gains a Scout section so the question *"how do I scout?"*
  answers itself in plain text too. `--json` gains `verdicts` and
  `tabs` fields.
- **Persistent surfaces**: branded header bar, sticky status banner,
  compressed analyse bar (languages · packages · top imports ·
  providers), and an always-visible `RichLog` result tail.
- **Modal dialogs preserved** from v0.4.1: splash, quit confirm, help
  (keymap rewritten for the new tabbed bindings), repo-path editor.
- **Tests**: 148 passing (up from 130). New `tests/test_tabs.py` (12
  tab-mount-and-one-action tests) and `tests/test_tab_navigation.py`
  (4 navigation tests). All v0.4.x splash, modal, evidence, and
  monorepo tests carry over.

## 0.4.1 - 2026-05-27

- **Mission Control v2** — Textual setup app redesigned end-to-end to match
  the designer's brand concept (mint `#24d6a8`, gold `#e3c26f`, blue `#7aa6ff`,
  navy `#0b1117`, steel `#25405c`). Branded one-line header bar replaces the
  default Textual header.
- New brand **splash screen** with a static Unicode radar (concentric rings,
  mint sweep wedge, mint/gold/blue pings) and the `FRONTIER · SCOUT` wordmark.
  Auto-dismisses after ~1.4s or on any keypress. Bypass with
  `frontier-scout setup --no-splash` or `FRONTIER_SCOUT_SKIP_SPLASH=1`.
- **Real modal dialogs** for quit confirmation (`q`), help (`?`), and
  repo-path editing (`/`) replace the old text-hijack patterns. Quit no
  longer wipes your last action's output; help is a proper keymap; the
  repo input is no longer always-on at the top of the screen.
- **Sticky status banner** carries transient warnings/info (resize hint,
  scanning progress, path errors) separately from the result log so
  messages don't overwrite each other.
- **`RichLog` result panel** keeps a timestamped, color-coded history of
  every action instead of a single overwrite-everything Static.
- **Focus-aware panels** — each panel border brightens to mint when its
  contents take focus (`:focus-within` CSS). Fingerprint and Providers
  panels are scrollable instead of silently truncated.
- **Evidence bars** — the v0.4.0 import-evidence top imports render with
  small Unicode bar visualisations (`fastapi  ████████  ×33`) so usage
  weight is obvious at a glance.
- **Button strip** replaces the OptionList for the safe-first-run actions;
  click or Tab+Enter to run.
- **README v2** — full rewrite on the `othneildrew/Best-README-Template`
  skeleton: centered hero (new dark `frontier-scout-hero.svg` distilled
  from the designer's concept), refreshed shields row (drops the stale
  `v0.1 alpha` badge), collapsible table of contents, About / Built With
  / Quickstart / Demo / Usage / Safety / Cost / Roadmap (now tracks v0.1
  through v0.4.1 as shipped) / Contributing / Acknowledgments.
- Bug fix: `_apply_diagnostics` no longer races on rebuilding the action
  strip — provider ordering is stable across same-session repo refreshes
  so the buttons stay mounted.

## 0.4.0 - 2026-05-27

- Profile detection now walks the repo up to three levels deep with a curated skip list (`node_modules`, `.venv`, `__pycache__`, `dist`, `build`, `.git`, etc.). Monorepos that put services under `backend/`, `lambda/`, `services/foo/` finally surface real `languages`, `package_managers`, and per-service `Dockerfile` paths.
- Added a deterministic, local-only import-evidence scanner backed by `tree-sitter-language-pack`. Reads Python and JavaScript/TypeScript source files via AST (never via LLM, never over the network), counts how many files import each top-level package, and promotes `frameworks` and `ai_tooling` from observed imports rather than substring matches on manifests.
- `DependencySpec.evidence_imports` records how many source files actually import each declared dependency. A small alias table maps PyPI distribution names to import names (`Pillow` → `PIL`, `python-dotenv` → `dotenv`, `scikit-learn` → `sklearn`, etc.).
- `ScoutProfile.import_evidence` summarises the top Python and JavaScript imports for quick triage. Surfaced in `frontier-scout setup --plain` / `--json` and in the Textual mission-control fingerprint panel.
- New `frontier-scout setup --no-imports` flag for the legacy fast path. The default `setup` scan completes in well under one second on real monorepos.
- `DependencySpec.manifest_path` now records the repo-relative path, so dependencies from `backend/requirements.txt` and `lambda/requirements.txt` are no longer collapsed.
- Stdlib modules (resolved via `sys.stdlib_module_names`) are filtered from the Python import surface so adoption signals show third-party tools only.
- `.understand-anything/` is now detected as an agent-config signal alongside `.cursor`, `.claude`, `AGENTS.md`, and `CLAUDE.md`.

## 0.3.0 - 2026-05-27

- Added `frontier-scout setup` terminal mission control: an interactive Textual UI with arrow-key navigation, Enter-to-run safe actions, repo-path input, URL paste, help overlay, and quit confirmation.
- Added `frontier-scout setup --plain` and `--json` outputs for limited terminals and automation, plus no-args TTY auto-launches the TUI while non-TTY no-args still prints help.
- Added read-only provider detection cards for Local deterministic, Ollama (probed at `/api/tags`), Claude CLI, Codex CLI, Anthropic API key, OpenAI API key, and GitHub token; secret values are never read or exposed.
- Added repo fingerprint diagnostics surfacing languages, package managers, containers, CI, agent configs, and dependencies inside the setup app.
- Added Scout Packs multi-select panel in the TUI with `space` to toggle; selection persists to `~/.frontier-scout/setup_state.json`. Mirrored via `frontier-scout setup --packs ai-devtools,mcp` for plain/JSON runs and surfaced as `[x]`/`[ ]` markers in plain output.
- Added typed repo-path input in the TUI that re-runs setup diagnostics in a background worker on Enter and refreshes the fingerprint, providers, and recommended actions.
- Made recommended next actions provider-aware: when no providers are detected the demo report leads; when an Anthropic or OpenAI key is present `dry_scan` and `evaluate_url` lead and the description notes that a live judge pass is available; when Ollama is reachable the detected model name surfaces in the dry-scan description.
- Added `textual>=8.2,<9` as a runtime dependency for the setup UI.

## 0.2.1 - 2026-05-26

- Reissued the v0.2 release line after the original GitHub `v0.2.0` tag name became unavailable during release recovery.
- Hardened the release workflow so manual trusted publishing can publish PyPI packages, while tag-triggered runs only create GitHub Release assets.
- No product behavior changes from `0.2.0`.

## 0.2.0 - 2026-05-26

- Added Living Scout Packs with seeded pack definitions, deterministic candidate lifecycle rules, pack CLI commands, and SQLite-backed pack state.
- Added dependency intelligence for PyPI/npm manifest parsing, cached OSV/PyPI/npm metadata, release-note classification, and safe dependency trial receipts.
- Added `frontier-scout deps scan`, `frontier-scout deps trial`, `frontier-scout packs list`, `frontier-scout packs show`, `frontier-scout packs refresh`, and `frontier-scout packs candidates`.
- Extended repo profiles with exact dependency names, ecosystems, specifiers, resolved versions, and dependency graph edges.
- Added Adoption Firewall v0 commands: `evaluate`, `trial`, `guard`, and `policy init`.
- Added local evidence-ledger tables for tools, evaluations, permission manifests, trial runs, lab results, policy findings, adoption decisions, and policy exceptions.
- Added deterministic MCP/tool capability classification and local policy decisions.
- Added trial receipt rendering and report sections for local try-before-trust records.
- Added structured JSON lab sidecars alongside Markdown transcripts.

## 0.1.0 - 2026-05-24

- Added installable `frontier-scout` CLI package.
- Added local demo/report flow with static HTML, Markdown, verdict JSON, cost breakdown, and judge trace artifacts.
- Added SQLite-backed local store under `~/.frontier-scout`.
- Repositioned the public project around local CLI + reports first, with agent/MCP surfaces later.
- Removed stale Slack/Lambda/S3 launch documentation from the public security and contribution model.
- Added GitHub issue templates, PR template, and GitHub Actions CI alignment.
- Added README visual preview assets, social preview artwork, and release metadata for the public v0.1 launch.
