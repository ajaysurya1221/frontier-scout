# Roadmap

Public, local-first, and ordered by launch value.

## v0.1 - launchable local radar

- Installable Python package with `frontier-scout` console entry point.
- `frontier-scout demo` for a no-key static report.
- `frontier-scout init --repo .` for stack-signal detection.
- `frontier-scout scan --dry-run` for seeded local output.
- Live Scout engine wired to the CLI for BYO-key scans.
- SQLite store under `~/.frontier-scout/db.sqlite`.
- Static HTML/Markdown report rendering.
- GitHub Actions CI: compile, non-live tests, secret scan.
- Clean public docs: README, SECURITY, CONTRIBUTING, AGENTS, CHANGELOG.

## v0.2 - Living adoption intelligence

- `frontier-scout evaluate <url>` for one-off, local try-before-trust evaluation.
- `frontier-scout trial <tool-or-url>` for durable sandbox trial receipts.
- `frontier-scout guard --repo .` for deterministic local/CI policy checks.
- `frontier-scout packs list/show/refresh/candidates` for living Scout Packs.
- `frontier-scout deps scan --repo .` for repo-relevant dependency security,
  hardening, and breaking-release findings.
- `frontier-scout deps trial <package> --from <ver> --to <ver>` for temp-dir
  upgrade receipts that never mutate the working tree.
- SQLite evidence ledger for tools, evaluations, permission manifests, lab results, trial runs, policy findings, adoption decisions, and exceptions.
- SQLite pack state for seeds, candidates, overrides, and dependency findings.
- Static report sections for Adoption Firewall trial receipts.
- Deeper stack detection from lockfiles, dependency manifests, MCP config,
  Docker files, and README signals.
- `frontier-scout latest` to print recent verdicts in a compact terminal view.
- `frontier-scout compare <tool>` to explain what changed since the prior verdict.
- Semantic search over past verdicts using a local, optional embedding index.
- Better report filtering by tier, category, risk, and fit.

## v0.3 - agent surfaces

- FastMCP server reading the local SQLite store.
- Claude Code / Codex / Cursor setup helpers that point agents at the local store.
- Optional output plugins for teams that want email, Slack, Discord, or generic webhooks.
- Taste feedback with `frontier-scout rate <id> +1/-1`, feeding a local preference model.

## v0.4+

- Cargo and Docker lab runtimes with runtime-specific safety gates.
- Optional E2B or similar sandbox for users who want stronger isolation than local subprocesses.
- GitHub Pages export for sharing a redacted static radar report.
- Team mode only if it can remain local-first and low-ops.

## Non-goals

- Hosted SaaS as the default product.
- Auto-installing recommended tools into a user's real project.
- Multi-tenant sync.
- Replacing human engineering judgment. Frontier Scout recommends what to inspect; the user decides what to adopt.
