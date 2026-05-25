# Frontier Scout

> Local-first try-before-trust for AI tools, agents, MCP servers, models, and risky engineering changes.

![python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)
![status](https://img.shields.io/badge/status-v0.1%20alpha-orange)
![license](https://img.shields.io/badge/license-MIT-blue)
![local-first](https://img.shields.io/badge/local--first-SQLite%20%2B%20static%20reports-0f766e)

![Frontier Scout report preview](docs/assets/frontier-scout-report-preview.png)

[Demo](#60-second-demo) · [What You Get](#what-you-get) · [Architecture](#architecture) · [Safety](#safety-model) · [Quickstart](#quickstart) · [Roadmap](ROADMAP.md) · [Security](SECURITY.md)

Frontier Scout answers the question technical teams now hit every week:

> Should this AI tool, agent, MCP server, model, or engineering change get any
> access to our code, shell, browser, network, or credentials?

It has three compatible surfaces:

- **Incident Change Scout**: a graph-aware engineering workflow that turns an
  incident ticket into cited context, a bounded remediation plan, approval
  interrupts, trace/audit logs, and an eval result.
- **AI Tool Radar**: a local adoption radar that turns public AI-tool signals
  into ADOPT / TRIAL / ASSESS / HOLD verdicts with source evidence.
- **Adoption Firewall**: evaluate, trial, and guard commands that record
  permission manifests and try-before-trust receipts before a tool touches a
  real project.

The posture is deliberately boring in the good way: CLI first, SQLite/local
files by default, static reports, no hosted telemetry, no hidden auto-installs,
and explicit approval before risky actions.

## 60-second demo

No API key. No Slack workspace. No cloud setup. Start with the engineering
workflow:

```bash
git clone https://github.com/ajaysurya1221/frontier-scout
cd frontier-scout
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make demo
open .scratch/incident-demo/answer.md
```

Incident demo writes:

- `.scratch/incident-demo/answer.md` — cited remediation answer.
- `.scratch/incident-demo/trace.jsonl` — local OpenTelemetry-shaped spans.
- `.scratch/incident-demo/audit.jsonl` — Cloudflare-style audit records.
- `.scratch/incident-demo/eval.json` — golden eval score.

Then run the AI tool radar demo:

```bash
frontier-scout demo
open demo/briefing.html
```

Radar demo writes:

- [`demo/briefing.html`](demo/briefing.html) — static executive radar.
- [`demo/briefing.md`](demo/briefing.md) — Markdown version for issues/docs.
- [`demo/verdicts.json`](demo/verdicts.json) — structured verdict payload.
- [`demo/cost-breakdown.md`](demo/cost-breakdown.md) — expected live-run spend shape.
- [`demo/judge-trace.md`](demo/judge-trace.md) — what the judge layer protects against.

## What you get

- **Incident Change Scout** for provenance-first incident analysis, graph-aware retrieval, bounded remediation planning, approval interrupts, and local evals.
- **AI ecosystem scouting** across GitHub releases, trending repos, MCP/skills sources, RSS, HN, Hugging Face, and a small arXiv slice.
- **ADOPT / TRIAL / ASSESS / HOLD verdicts** with risk, stack fit, readiness, adoption cost, provenance, and next action.
- **Adoption Firewall** commands for try-before-trust evaluation: local evidence ledger, permission manifests, sandbox trial receipts, and CI-friendly guard checks.
- **Optional Opus judge pass** that vetoes patch-release noise, incident-as-tool mistakes, unsupported claims, and weak ADOPT calls.
- **Repo-aware stack detection** from common manifests and agent config files.
- **Polyglot lab runner** for Python, Node, and Hugging Face packages with hermetic subprocess execution.
- **Local history** in SQLite so future CLI/MCP/plugin surfaces can compare what changed over time.

## Why not just use newsletters or GitHub Trending?

| Option | What it gives you | What is missing |
|---|---|---|
| Newsletters | Good awareness | Not repo-aware, not source-verifiable, rarely actionable. |
| GitHub Trending | Popularity signal | No risk/fit/adoption-cost judgment. |
| Manual research | Highest nuance | Slow, inconsistent, easy to skip when busy. |
| Frontier Scout | Source-backed verdicts and lab next steps | Requires your API key for live scans. |

## Architecture

```mermaid
flowchart LR
  Ticket["Incident ticket"] --> DCG["Typed DCG runtime"]
  Corpus["Seed corpus"] --> Memory["Memory + graph"]
  Memory --> Authz["ReBAC check"]
  Authz --> Retrieval["Hybrid retrieval"]
  Retrieval --> Context["Context compiler"]
  Context --> Gateway["Model gateway"]
  Gateway --> DCG
  DCG --> Approval["Approval interrupt"]
  DCG --> Audit["Trace + audit + eval"]
  Sources["Public sources"] --> Scout["Scout funnel"]
  Scout --> Score["Sonnet score pass"]
  Score --> Verdict["Sonnet verdict pass"]
  Verdict --> Judge["Optional Opus judge"]
  Judge --> Validators["Deterministic validators"]
  Validators --> SQLite["Local SQLite"]
  SQLite --> CLI["CLI"]
  SQLite --> Report["Static report"]
  SQLite --> MCP["Future MCP/plugin surface"]
  CLI --> Lab["Hermetic lab"]
```

The current engine lives in [`scripts/`](scripts/). The installable CLI lives
in [`frontier_scout/`](frontier_scout/). `scripts/` remains importable so the
existing Scout and lab logic can be packaged without a risky rewrite.

## Quickstart

Install from a checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
frontier-scout --help
```

Initialize local state and detect stack signals:

```bash
frontier-scout init --repo .
```

Run a free seeded scan:

```bash
frontier-scout scan --dry-run --repo .
frontier-scout report --input demo/verdicts.json --output demo/briefing.html
```

Run a live scan:

```bash
export ANTHROPIC_API_KEY=...
frontier-scout scan --repo .
frontier-scout report
```

Try-before-trust a single tool before granting it project permissions:

```bash
frontier-scout evaluate https://github.com/modelcontextprotocol/servers
frontier-scout trial browser-use/browser-use --url https://github.com/browser-use/browser-use --dry-run
frontier-scout guard --repo .
```

`evaluate` records source-backed local evidence and a permission manifest.
`trial --dry-run` writes an adoption receipt without installing anything.
`guard` checks the local evidence ledger for risky tools that still need a
stored trial receipt.

After the first PyPI publish, the expected package install paths are:

```bash
pipx install frontier-scout
uvx frontier-scout demo
```

Until then, the checkout install above is the supported path. An
`npx frontier-scout` wrapper is intentionally a later distribution layer, not
the core implementation.

## Safety model

Frontier Scout handles untrusted public content and can optionally execute
untrusted packages in the lab, so the safety rails are load-bearing:

- Source text is treated as untrusted data, not instructions.
- Tool names are checked against the source pool to reduce hallucinated verdicts.
- Source URLs must pass a domain allowlist.
- Incident and breach headlines are blocked from becoming tool recommendations.
- ADOPT requires enough readiness evidence or gets demoted.
- Adoption Firewall fails closed on unknown MCP/tool capability surfaces.
- `guard` never modifies the repo; it only reads local evidence and policy.
- Lab subprocesses receive a stripped environment, wall-clock timeout, size caps, and generated-script secret scanning.

See [SECURITY.md](SECURITY.md) for the threat model.

## Cost

The offline demo is free. A normal live weekly scan is designed to stay cheap:

| Component | Typical cost |
|---|---:|
| Sonnet score pass | ~$0.15 |
| Sonnet verdict pass | ~$0.04 |
| Optional Opus judge | ~$0.12 |
| **Weekly scan** | **~$0.30** |

Set `JUDGE_ENABLED=false` to skip the Opus judge when you want the cheapest
possible run.

## Development

```bash
make setup
make demo
make test
make eval
make audit
python -m compileall scripts outputs tests frontier_scout
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
frontier-scout demo
frontier-scout scan --dry-run
```

CI runs compile checks, non-live tests, and a tracked-file secret scan.

## Release

For v0.1 patch releases:

1. Bump `project.version` in `pyproject.toml`.
2. Update the matching section in `CHANGELOG.md`.
3. Merge to `main`.
4. Push annotated tag `vX.Y.Z`.

Tag pushes trigger `.github/workflows/release.yml`, which builds distributions,
publishes to PyPI via trusted publishing, and creates a GitHub Release from
the matching changelog section.

## Roadmap

See [ROADMAP.md](ROADMAP.md). The short version:

- **v0.1** — local radar, Adoption Firewall, Incident Change Scout, static reports, SQLite, CI, Docker demo, and public docs.
- **v0.2** — deeper Adoption Firewall hardening, richer repo-aware stack detection, and stronger live-provider smoke tests.
- **v0.3** — MCP/plugin surfaces and optional output integrations on top of the same local evidence store.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). The fastest useful PRs improve the
CLI/report path, validator coverage, source quality, or lab isolation.
Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE)
