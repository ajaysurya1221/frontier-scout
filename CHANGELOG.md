# Changelog

## Unreleased

- No unreleased changes yet.

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
