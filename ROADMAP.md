# Roadmap

Public, opinionated, ordered. Items at the top are the next thing in line.

## v0.1 — the launchable slice (in progress)

Detailed phase table in [`README.md`](README.md#status). The headline:

- `fs_cli/` — Typer CLI: `init`, `scan`, `latest`, `lab`, `where`
- `fs_cli/db.py` — SQLite store at `~/.frontier-scout/db.sqlite`
- `fs_cli/stack_detect.py` — auto-detect the user's stack on first run
- `fs_cli/scheduler.py` — cron / launchd / Task Scheduler install
- `fs_mcp/server.py` — FastMCP server exposing six tools
- `outputs/` — terminal (Rich) + static HTML report
- `skill/` — Claude Code skill bundle that lands under `~/.claude/skills/`
- `pyproject.toml`, GitHub Actions test workflow, README polish

## v0.2

- **Semantic search over past verdicts** — bring back lightweight
  embeddings (only for the on-demand `search` MCP tool, not at scan time).
- **Email digest output** — opt-in weekly email when the user prefers
  pull-from-inbox over pull-from-agent.
- **`compare <tool>` MCP tool** — when the SQLite store has a prior
  verdict on the same tool, return the delta (was ASSESS in March, now
  TRIAL — what changed?).
- **`evaluate <tool>` MCP tool** — on-demand deep evaluation that runs
  the full score + verdict + judge funnel for a single user-named tool.

## v0.3

- **`frontier rate <id> +1/-1`** — CLI taste-model surface. Ratings
  feed a small bandit that biases future scoring within the
  "never silence novelty" guardrails the original taste model had.
- **Output plug-ins** — Slack, Discord, generic webhook. Each is a small
  module under `outputs/` behind a feature flag.
- **App Home tab equivalent** — for users who do use Slack and want a
  pinned weekly dashboard, ship the Slack plug-in with an App Home view.

## v0.4+

- **Cargo + Docker lab runtimes** — extend the polyglot dispatcher.
  Each one's a substantial own-its-own change (Rust toolchain in the
  pipeline image; per-image size caps and `services: [docker]` for
  Docker), so they're deferred.
- **E2B sandbox** — move the lab's untrusted-package execution into a
  proper per-run sandbox once the polyglot dispatcher's surface area
  justifies the operational weight.
- **Per-user dashboards** — for teams sharing one repo, optional
  per-user taste-model state.

## Explicitly NOT on the roadmap

- **Hosted SaaS.** Frontier Scout is local-only — your verdicts live on
  your laptop, your stack profile never leaves the machine.
- **Auto-installing recommended tools.** The lab runs a synthetic
  test. The user decides what to install for real. Always.
- **Agent frameworks (CrewAI / AutoGen / LangGraph) in the scheduled
  scan loop.** Linear Python is the architectural choice.
- **Multi-tenancy.** One radar per user, one user per radar.
