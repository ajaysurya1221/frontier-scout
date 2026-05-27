# Changelog

## Unreleased

- No unreleased changes yet.

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
