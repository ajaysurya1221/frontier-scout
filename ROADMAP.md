# Roadmap

Public, opinionated, ordered. Items at the top are the next thing in line.

## Near-term

- **🧪 Lab → Jira spike auto-creation** — today the 🧪 button writes a markdown task to `.scratch/labs/`. Adding a Jira REST call to also open a sprint-spike ticket with the tool name, source URL, requester, and a 3-day SLA. Without this, the queue can pile up silently. ~1 hour of work in `scripts/lab_from_slack.py` once Jira credentials are added.
- **🧪 Lab findings → Mem0 auto-seed** — when an engineer commits findings to `skills-log.md`, a GitHub Actions workflow seeds the finding into Mem0 so `/recall` surfaces it within minutes (today it only feeds the monthly Synthesizer + next Scout). Closes the "we waited a month for the next briefing to know" gap.
- **`chromadb` Lambda Layer** — bundle Chroma + ONNX wheels in a Lambda Layer so `/recall` returns real semantic search instead of "unavailable". Needs Docker to cross-build for `manylinux2014_x86_64`. ETA: one Saturday morning.
- **Mem0 prior-tier deltas in verdict cards** — *"was ASSESS in March, now TRIAL — what changed?"* The data is in Mem0 already; surfacing it in the card is renderer work. Genuine product value, not chrome.
- **Operator preflight as a GitHub Actions PR gate** — `scripts/preflight.py` runs cleanly on every PR, blocking schedule-enable changes that would break.
- **Adversarial source corpus** — a small curated bank of prompt-injection-shaped fake RSS items the test suite scores against, asserting they never produce verdicts.

## Mid-term

- **App Home dashboard** — Slack's per-bot persistent view: this week's verdicts pinned at top, full tech-radar searchable, monthly cost trend. Adds `app_home_opened` handler to the same Lambda. ~1 hour of work.
- **Inline weekly chart** — matplotlib bar chart of verdicts-by-tier rendered via `files.upload`. Adds ~30 MB to Lambda zip → needs a layer for matplotlib + dependencies.
- **Multi-channel routing** — security findings to a different channel; everything else to the default. First real pipeline branch — at this point the linear architecture starts to earn LangGraph.
- **Human-feedback signal loop** — track Slack reaction counts per verdict over time; feed back into scoring weights. Requires 4-8 weeks of reaction data first.

## Long-term

- **"Lab agent"** — clicking 🧪 spawns an actual agent that iteratively probes the tool's API, writes findings, and commits to `skills-log.md`. This is where an agent framework finally earns its keep.
- **Cross-org radar federation** — multiple deployments sharing a sanitized "what we collectively evaluated" public Mem0 view. Public-good signal.
- **Custom workspace emoji** — `:radar-adopt:` `:radar-trial:` etc. instead of relying on standard tier circles. Tiny UX polish; needs workspace admin upload.

## Explicitly NOT on the roadmap

- Agent frameworks (CrewAI / AutoGen) in the scheduled pipelines. Linear Python is the architectural choice.
- New LLM vendors beyond Anthropic + OpenAI. SOC2 vendor surface stays minimal.
- A custom UI dashboard outside Slack. The artifacts (`tech-radar.md`, `briefings/`, `quality-log.jsonl`) are the dashboard.
- Multi-tenancy. One radar per Slack workspace.
