# Roadmap

Public, local-first, and **demand-gated** — forward work ships only on real,
workflow-shaped pull, not on a feature wishlist. This repo is a **research
preview**: technically coherent, **not** market-validated. No PMF or adoption claim.

## Where we are — sanctioned MCP-server packs (research preview)

The current product is **sanctioned MCP-server packs for coding assistants
(Claude Code first)**: repo-rank approved MCP servers into a **static** capability +
policy safety map, gate sanctioning by risk, then **export a Claude Code
managed-config fragment** (`allowedMcpServers` / `deniedMcpServers` + a project
`.mcp.json`) that an admin deploys. Local, keyless, offline by default.

Shipped today:

- `frontier-scout packs candidates --repo . --client claude-code` — repo-ranked
  MCP servers (curated offline pack, or the live MCP registry with `--discover`),
  ranked against your stack with a local tree-sitter pass that never reads your source.
- `frontier-scout packs sanction <server> --repo .` — risk-gated approval
  (high-risk servers need `--acknowledge-risk`); `unsanction` reverses it.
- A **static safety map** per server (`safety_summary.py`): capability
  classification (read / write / network / shell / credential) + a policy verdict.
  **No MCP server is started or executed in the pack flow.**
- `frontier-scout packs export --client claude-code --target ./out` — the approved
  set as a Claude Code managed-config fragment for admin review. It **emits** config;
  it does **not** enforce runtime policy.
- `frontier-scout packs proof <server>` — the A/B/C proof variants
  (approval-only / static safety summary / formal static receipt) used to learn which
  artifact a design partner would actually keep.
- `frontier-scout stats` — the local, opt-in sanctioned-pack funnel
  (candidates → safety → sanction → export).

### Also shipped (research preview) — agent adoption firewall + audit trail

A **static, advisory** sibling surface under `frontier-scout agent`, reusing the same risk taxonomy and
profiler. It is, like the packs flow, a **research preview** — built to make the wedge concrete, **not** a
claim of validation, and **not** a substitute for the design-partner pull described below.

- `frontier-scout agent scan` — enumerate repo agent-risk surfaces (agent/MCP configs, CI, deploy config,
  protected paths, secret-likely files **by name only**) + detected test/lint/build checks.
- `frontier-scout agent policy init` / `policy explain` — a conservative `frontier-scout.policy.json`.
- `frontier-scout agent check "<task>"` — pre-check a *proposed* task → `allow / needs_approval / block`
  with reasons. **Executes nothing.**
- `frontier-scout agent receipts list` / `show` — local JSON audit receipts.
- `frontier-scout agent export claude|agents-md|pr-checklist` — advisory policy snippets (emit, not enforce).

It **emits** policy and evidence; it does **not** enforce at runtime, run any agent task, start an MCP
server, hit the network, or read secret values. See
[docs/examples/agent-firewall/](docs/examples/agent-firewall/).

The local-first **adoption radar** that powers ranking, the safety map, and the
TUI (`scout` / `evaluate` / `dossier` / `lab` / `trial` / `guard` / `policy` /
`report` / Mission Control) is the **engine underneath** the packs product — kept
as a legacy surface, not the headline. Its shipped history is below.

<details>
<summary><b>Shipped — the radar engine underneath (history)</b></summary>

- **v0.1** — Installable `frontier-scout` package; `demo` no-key static report;
  `init` stack-signal detection; `scan --dry-run`; live Scout engine; SQLite store;
  static HTML/Markdown reports; GitHub Actions CI (compile, non-live tests, secret scan).
- **v0.2** — Living Scout Packs; `evaluate` / `trial` / `guard`; dependency
  intelligence (`deps scan` / `deps trial`); SQLite evidence + pack state; Adoption
  Firewall receipts; deeper stack detection.
- **v0.4.0** — Monorepo profile walker + tree-sitter import-evidence scanner
  (Python & JS/TS).
- **v1.0.0** — Mission Control: every CLI capability gets a TUI surface, scout-first
  landing.
- **v1.1.0** — Global setup wizard, cron automation, notifications, Go / Rust / Ruby
  coverage.
- **v1.4.0** — Universal LLM provider, RLAIF fit-grounding loop, honest per-provider
  costs.
- **v1.5.0 – v1.7.0** — Mission Control 8-tab command center + command palette,
  full mouse ↔ keyboard parity, permission map, repo switcher, two-tier scout/judge
  split, `openai-compatible` provider.
- **v1.8.x** — Mission Control v5/v6 (Adoption Matrix, segmented gauges, architecture
  profile), CLI deep-probe for provider availability.

</details>

## What's next — validation before more building

The next milestone is **not** a feature; it is **design-partner validation**. The
standing rule is: don't build V1 and don't run more internal gates — earn the next
build with real, workflow-shaped pull from real people (someone routing the Claude
export through an actual process, or two people independently asking for the same
export target). `packs proof` + `frontier-scout stats` exist to capture that signal.

## Demand-gated V1 (build only on validated pull)

These are weighed in [`docs/pivot/`](docs/pivot/) and the
[open issues](https://github.com/ajaysurya1221/frontier-scout/issues); none are built,
and none ships ahead of validation:

- **A second export client** — Copilot + a GitHub allow-list exporter (the first
  non-Claude target), if the pull is for it specifically.
- **Docker MCP catalog** as a candidate source.
- **A behavioral MCP probe** for high-risk servers only — actually exercising a
  server in the hermetic lab to back a sanction with runtime evidence, layered on top
  of the static map (today every pack-flow read is static).
- **A non-blocking notifier** for sanction/policy drift (CI-friendly, never blocking).
- **An interactive TUI packs flow** — driving candidates → sanction → export from
  Mission Control.

## Non-goals

- Hosted SaaS as the default product.
- Auto-installing recommended tools (or sanctioned MCP servers) into a user's real
  project.
- Multi-tenant sync.
- Replacing human engineering judgment. Frontier Scout recommends what to inspect and
  emits config to approve; the user decides what to adopt and the admin deploys it.
