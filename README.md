# frontier-scout

> the Claude Code skill that tells your agent which new skills,
> MCP servers, and frameworks to plug in this week.

![python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)
![status](https://img.shields.io/badge/status-v0.1%20build%20in%20progress-orange)
![license](https://img.shields.io/badge/license-MIT-blue)

Five of the top-20 fastest-growing GitHub repos this week have "skills" in
the name. The Claude Code ecosystem keeps shipping MCP servers, slash
commands, and agent frameworks faster than any newsletter can keep up with.

**Frontier Scout is an AI-tooling radar that lives inside your AI coding
agent.** Once a week it scans the parts of the ecosystem that actually
matter to a solo builder — anthropics/skills, mattpocock/skills,
awesome-mcp-servers, Claude Code release notes, agent-framework releases —
forms an opinion (ADOPT / TRIAL / ASSESS / HOLD with risk and stack-fit),
and exposes it to Claude Code / Cursor / Codex through an MCP server.

You ask: *"any new MCP worth trying for Postgres?"*
Your agent calls Frontier Scout and answers with a verdict.
You say: *"lab-test the second one."*
The polyglot lab runner pulls it, executes it in a hermetic subprocess,
and reports back what actually worked.

---

## status

**v0.1 build in progress.** The engine — scout funnel, Sonnet score +
verdict passes, optional Opus RLAIF judge, polyglot lab runner
(Python / Node / HuggingFace), policy validators — lives under
[`scripts/`](scripts/) and runs today. The CLI shell + SQLite store +
MCP server + Claude Code skill bundle that turn this into something you
can `pipx install` are landing across the next few commits.

| Phase | What lands | Status |
|---|---|---|
| 1 | Strip legacy Slack / Lambda / Bitbucket surface | ✅ shipped |
| 2 | Reshape verdict schema (`risk` + `fit`, new categories) + reprompt for solo builders | ✅ shipped |
| 3 | `fs_cli/` foundation — SQLite store, stack auto-detect, scheduler, first-run wizard | ⏳ next |
| 4 | `outputs/` — terminal (Rich) + HTML report | ⏳ |
| 5 | `fs_mcp/server.py` — FastMCP server (6 tools) | ⏳ |
| 6 | `skill/` — Claude Code skill bundle | ⏳ |
| 7 | `pyproject.toml` + GitHub Actions test workflow | ⏳ |
| 8 | README polish + SECURITY trim | ⏳ |

Until Phase 3 lands, the only entry points that work are:

```bash
python scripts/demo.py                          # render demo/briefing.html from fixtures
ANTHROPIC_API_KEY=… python scripts/scout.py     # live scan, prints results
pytest -q                                       # lab regressions + validator gates
```

---

## what it is (and isn't)

| | |
|---|---|
| **Bullseye user** | solo AI builders shipping with Claude Code / Cursor / Codex / Aider |
| **Primary surface** | a Claude Code skill backed by an MCP server. The CLI is the engine; the agent is the UI. |
| **Storage** | a single SQLite file at `~/.frontier-scout/db.sqlite`. No daemon, no central service. |
| **Cost** | ~$2 / month at default settings, BYO Anthropic key. Opus judge optional (`JUDGE_ENABLED=false` to skip). |
| **What it's not** | not a chatbot, not a newsletter, not enterprise, not auto-installing anything. The agent asks; the user decides. |

---

## how it will work (end-to-end, once Phase 3+ lands)

### day 0 — install

```bash
pipx install frontier-scout
frontier-scout init
```

The init wizard:

1. **Auto-detects your stack** (with consent) — walks `~/projects` for
   `package.json`, `pyproject.toml`, `Cargo.toml`, `~/.config/claude/mcp.json`,
   and writes a `stack.yaml` profile you can edit anytime.
2. **Schedules the weekly scan** — installs a cron entry (Linux),
   launchd plist (macOS), or scheduled task (Windows).
3. **Hooks Claude Code** — writes the MCP server config into your
   Claude Code settings.

### day-to-day — inside Claude Code

```
you  > any new MCP servers worth trying for postgres?
claude  *calls frontier-scout MCP → verdicts_by_category("mcp_server")*
claude  > Three recent verdicts:
        1. modelcontextprotocol/postgres-mcp — TRIAL — fit=high
        2. crystaldba/postgres-mcp — ASSESS — fit=medium
        3. neondatabase/mcp-server-neon — TRIAL — fit=high
you  > lab-test the first one against my stack
claude  *calls frontier-scout.try_before_install(...)*
claude  > Install ok, basic introspection works. Read-only mode connected
        to a throwaway DB, returned schema for 3 tables. Worth a real trial.
```

### weekly — the scheduled scan

Sunday 8pm, a single Python process wakes, runs 60–120 seconds, writes
verdicts to SQLite, exits. No always-on daemon. The MCP server is
launched on-demand by Claude Code and exits when the client disconnects.

---

## what's interesting under the hood

- **Honest funnel.** Sonnet score pass → Sonnet verdict pass → optional
  Opus RLAIF judge → Pydantic policy gates (URL allowlist, anti-injection,
  incident-as-tool veto). See [`scripts/scout.py`](scripts/scout.py),
  [`scripts/judge.py`](scripts/judge.py), [`scripts/validators.py`](scripts/validators.py).
- **Polyglot lab.** One dispatcher, three runtimes: pip + python,
  npm + node, huggingface_hub + transformers (config + tokenizer only,
  no inference, 5 GB weight cap). Hermetic env strips every secret from
  the child process. Backed by [`tests/test_lab.py`](tests/test_lab.py)
  including a live subprocess check that the child can't read the
  parent's API keys.
- **Risk + fit, not SOC2.** v0.1 dropped the enterprise SOC2 framing and
  replaced it with a solo-builder-relevant axis: `risk = {low|medium|high}`
  × `fit = {high|medium|low}` against the user's detected stack.
- **Narrow source funnel.** 220-item cap across the parts of the
  ecosystem this audience actually cares about — anthropics/skills,
  trending `*/skills` repos, awesome-mcp-servers, Claude Code releases,
  agent framework releases, HF model drops (capped). Generic AI
  newsletters: out.

---

## non-goals (explicit)

- **Not a chatbot.** Your agent uses it. You don't talk to it.
- **Not a newsletter.** Email / Slack / Discord output is a v0.3 plug-in
  if there's demand. The primary surface is the MCP server.
- **Not enterprise.** No SSO, teams, SOC2 mode, shared dashboards.
- **Not auto-installing anything.** The lab runs a synthetic test in a
  sandbox. You decide what to install for real.
- **Not a hosted service.** Everything runs on your laptop.

---

## roadmap

See [ROADMAP.md](ROADMAP.md). Short version:

- **v0.1 (in progress)** — CLI + MCP + Claude Code skill, the launchable slice.
- **v0.2** — semantic search over past verdicts, email digest output,
  `compare <tool>` MCP tool.
- **v0.3** — `frontier rate <id> +1/-1` taste model,
  Slack / Discord / generic-webhook outputs.
- **v0.4+** — Cargo + Docker lab runtimes, optional E2B sandbox.

---

## security & lab isolation

See [SECURITY.md](SECURITY.md) for the full threat model. One-line summary:
the lab runs untrusted package code in a hermetic subprocess (no API keys
reach the child; verified by a live test in `tests/test_lab.py`), under a
wall-clock timeout, with a daily run cap and a USD cap.

---

## contributing

Open an issue first if you're adding a new source, a new lab runtime, or
a new MCP tool — the funnel and the lab's safety model both have
non-obvious invariants. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

[License: MIT](LICENSE)
