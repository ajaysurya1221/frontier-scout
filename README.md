```
███████╗██████╗  ██████╗ ███╗   ██╗████████╗██╗███████╗██████╗
██╔════╝██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝██║██╔════╝██╔══██╗
█████╗  ██████╔╝██║   ██║██╔██╗ ██║   ██║   ██║█████╗  ██████╔╝
██╔══╝  ██╔══██╗██║   ██║██║╚██╗██║   ██║   ██║██╔══╝  ██╔══██╗
██║     ██║  ██║╚██████╔╝██║ ╚████║   ██║   ██║███████╗██║  ██║
╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚══════╝╚═╝  ╚═╝

███████╗ ██████╗ ██████╗ ██╗   ██╗████████╗
██╔════╝██╔════╝██╔═══██╗██║   ██║╚══██╔══╝
███████╗██║     ██║   ██║██║   ██║   ██║
╚════██║██║     ██║   ██║██║   ██║   ██║
███████║╚██████╗╚██████╔╝╚██████╔╝   ██║
╚══════╝ ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝
```

**Frontier Scout: an AI adoption radar for engineering teams**

_A practical adoption radar for AI-native engineering teams._

![python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)
![models](https://img.shields.io/badge/models-Sonnet_4.6_+_Opus_4.7-d97757)
![cost](https://img.shields.io/badge/cost-~%242%2Fmonth-success)
![tests](https://img.shields.io/badge/tests-130_passing-brightgreen)
![runtime](https://img.shields.io/badge/runtime-GitHub_Actions_+_AWS_Lambda-blueviolet)
![license](https://img.shields.io/badge/license-MIT-blue)

[Demo](#60-second-demo) · [What You Get](#what-you-get) · [Architecture](#architecture) · [Safety](#safety-model) · [Quickstart](#quickstart) · [Roadmap](ROADMAP.md) · [Security](SECURITY.md)

---

Hundreds of AI tools, agent frameworks, model releases, and research drops appear every week. Most are irrelevant to your stack. A few are worth testing before competitors notice them.

**Frontier Scout is an adoption radar for AI-native engineering teams.** It watches the exploding AI ecosystem, filters the noise, judges what matters against your stack and security bar, and turns the best signals into concrete adoption actions: adopt, trial, assess, or hold.

**Why star this repo**

| Signal | What makes it different |
|---|---|
| **Decision-grade radar** | Every item becomes ADOPT, TRIAL, ASSESS, or HOLD with SOC2 posture, readiness, adoption cost, and next action. |
| **Judge before publish** | Draft verdicts are reviewed by an Opus judge, then checked by deterministic validators for incidents, hallucinated tools, unsafe URLs, and prompt injection. |
| **Action loop built in** | Slack buttons queue labs, run deep evaluations, and compare against memory so the radar becomes an operating rhythm, not a newsletter. |

```bash
# No Slack, no AWS, no API keys
python scripts/demo.py && open demo/briefing.html
```

---

## Why Frontier Scout Exists

The goal is simple: give engineering leadership a weekly, evidence-backed view of which AI tools are worth researching, testing, and adopting.

The AI ecosystem is too fast for manual radar meetings and too noisy for raw feeds. A useful engineering radar needs three things at once: early signal, conservative judgment, and a direct path from "interesting" to "someone tested this on a real problem."

Frontier Scout turns public launches, releases, trending repos, newsletters, arXiv papers, HN posts, and HuggingFace movement into a weekly briefing that a real platform team can act on.

### Why not just use...

| Alternative | Where it breaks | What Frontier Scout adds |
|---|---|---|
| **Newsletters** | Great awareness, weak fit to your stack. | Stack-aware verdicts, SOC2 posture, adoption cost, and next actions. |
| **GitHub Trending** | Strong velocity signal, lots of irrelevant repos. | Stratified source caps, judge vetoes, policy gates, and prior-memory filtering. |
| **Manual radar docs** | High quality, low freshness. | Scheduled Scout, daily Pulse, monthly synthesis, and append-only audit logs. |
| **A Slack bot script** | Fun demo, brittle production story. | Retry/backoff, dead letters, secret scanning, preflight checks, and signed Lambda interactivity. |

---

## 60-Second Demo

Run the local demo when you want to understand the product without setting up Slack, AWS, GitHub Actions, or API keys.

```bash
git clone https://github.com/ajaysurya1221/frontier-scout.git
cd frontier-scout
python scripts/demo.py
open demo/briefing.html
```

The demo generates:

- `demo/briefing.html`: Slack-style preview that opens in any browser.
- `demo/briefing.md`: markdown briefing as it would land in the repo.
- `demo/judge-trace.md`: judge decisions, including veto reasons.
- `demo/cost-breakdown.md`: per-component cost table.
- `demo/quality-log.jsonl`: sample funnel, judge, and retry stats.

### Sample briefing excerpt

```md
# Frontier Scout — Weekly Briefing · 2026-05-21
> Scanned **377** items · **350** considered after dedup + Mem0 prior-filter · **6** verdicts after RLAIF judge pass.

### 🔥 anthropics/skills — 🟢 ADOPT — Tools & Frameworks — ✅ SOC2-safe
What: Anthropic's official public repository of Agent Skills.
Why it matters: Skills primitives accelerate reusable agent capabilities without reinventing plumbing.
Next action: Lab one skill inside an existing LangGraph node.
```

---

## What You Get

**Scout: weekly intelligence briefing**

Scans the AI/ML ecosystem every Monday, dedupes and prior-filters the source pool, caps the candidate set by source group, emits judged verdicts, writes a markdown audit copy, updates memory, and posts the Slack thread.

**Pulse: daily Tier-S alerts**

Checks high-signal release surfaces daily. Silent on boring days, posts only when a candidate clears the Tier-S threshold and survives judge + policy gates.

**Synthesizer: monthly strategy layer**

Looks across the month of verdicts and labs to summarize momentum, blind spots, stalled ideas, and the next best area of focus.

**Slack-native operating loop**

Each verdict card has buttons for lab, deep evaluation, and comparison. Slash commands make the radar queryable from any Slack channel.

**Audit and safety rails**

Every API call, quality decision, retry, cost, briefing, and generated artifact is written to repo-visible files so the system is inspectable instead of magical.

### Pipeline map

| Pipeline | When | Produces |
|---|---|---|
| `scout` | Mon 03:30 UTC | Weekly Slack briefing + `briefings/YYYY-MM-DD.md` |
| `pulse` | Daily 02:30 UTC | Tier-S alert or silent run |
| `synthesizer` | 1st of month | `MONTHLY_SYNTHESIS.md` + Slack thread |
| `cost-report` | Sun 12:00 UTC | Month-to-date spend summary |
| `lab-from-slack` | Button click | Pulls the tool, runs a synthetic stack-shaped test in a hermetic subprocess, posts insights in the verdict thread + full transcript in `.scratch/labs/` |
| `evaluate-from-slack` | Button click | Deep evaluation reply in thread |
| `deploy-lambda` | Manual | Slack interactivity Lambda deploy |
| `verdict-quality` | PR gate | Secret scan + unit tests |

---

## Architecture

```text
47 source streams
  RSS, labs, GitHub, HN, HuggingFace, arXiv
        |
        v
Dedupe + Mem0 prior filter
        |
        v
Stratified cap
  keep source diversity under token budget
        |
        v
Sonnet 4.6 score pass -> Sonnet 4.6 verdict pass
        |
        v
Opus 4.7 RLAIF judge
  veto, retier, promote, rate readiness
        |
        v
Deterministic policy gates
  Pydantic, URL allowlist, anti-injection
        |
        v
Artifacts
  Slack, briefings, Mem0, quality-log, cost ledger
        |
        v
GitHub repo  (single source of truth)
        |
        |  Lambda fetches repo tarball via GH_TOKEN (cold-start)
        v
AWS Lambda Function URL
        |
        +-> Slack slash commands: /radar, /recall
        |
        +-> Slack buttons: lab, evaluate, compare
                |
                v
        GitHub Actions workflows
```

The architecture is intentionally linear. No agent framework is needed for the scheduled runs: fetch, score, verdict, judge, validate, publish, log. The only always-on service is the small Lambda used for Slack interactivity.

### The 47-source funnel

| Layer | Sources |
|---|---|
| **First-party labs** | Anthropic, OpenAI, DeepMind, HuggingFace, Mistral |
| **Curated newsletters** | TLDR AI, AINews, Ben's Bites, The Batch, Import AI, Latent Space |
| **Practitioner blogs** | Simon Willison, Eugene Yan, Raschka, AI Tidbits, Cameron Wolfe, HF Papers |
| **Community** | r/MachineLearning, r/LocalLLaMA, HN smart-filter |
| **Adoption velocity** | GitHub Trending, HF likes-7d, PapersWithCode |
| **Product discovery** | ProductHunt AI category |
| **Watchlist** | LangChain, LangGraph, vLLM, Ollama, Modal, and other named repos |
| **Research** | arXiv `cs.AI`, `cs.CL`, `cs.LG` |

### RLAIF judge strategy

The judge is the precision layer. Sonnet generates strong drafts; Opus reviews them like a strict principal engineer.

1. **Adaptive thinking attempt:** Opus 4.7 reviews the drafts with tool choice on auto.
2. **Forced tool fallback:** if the thinking pass does not emit structured `tool_use`, retry without thinking and force `critique_verdicts`.
3. **Fail closed:** if both attempts fail, every draft is vetoed and the run is marked low-confidence.

The judge can veto, retier, promote missed items, assign severity, and set a 5-slot readiness meter.

---

## Slack Experience

The weekly briefing is designed to be scanned by leadership and acted on by engineers. A compact parent message gives the funnel, cost, and judge read; the thread contains one decision card per verdict.

```text
┌────────────────────────────────────────────────────────────────────┐
│ Frontier Scout — Weekly Briefing · 2026-05-21                       │
├────────────────────────────────────────────────────────────────────┤
│ 377 scanned  ·  250 considered  ·  8 shipped                      │
│ Judge: HIGH  ·  Cost: $0.31  ·  Runtime: 232s                     │
│ Severity: 1 critical  ·  5 high  ·  2 standard                    │
│                                                                    │
│ Judge's read                                                       │
│ Strong pass. Vetoed two noise items, promoted one stack-direct hit.│
│                                                                    │
│ TL;DR                                                              │
│   ADOPT  · 1                                                       │
│     1. anthropics/skills      Tools           SOC2-safe            │
│   TRIAL  · 4                                                       │
│     2. Gemini 3.5 Flash       Frontier        SOC2-conditional     │
│     3. Forge Guardrails       Agents          SOC2-conditional     │
│   ASSESS · 2                                                       │
│   HOLD   · 1                                                       │
└────────────────────────────────────────────────────────────────────┘
```

Thread card example:

```text
┌─ Verdict #1 ───────────────────────────────────────────────────────┐
│ ADOPT · critical · Tools & Frameworks · SOC2-safe                  │
│ Readiness: ▰▰▰▰▰ 5/5                                               │
├────────────────────────────────────────────────────────────────────┤
│ anthropics/skills                                                  │
│ Official reusable Agent Skills for Claude-based agents.            │
│                                                                    │
│ Why it matters                                                     │
│ Reusable capability modules can shorten implementation time for    │
│ retrieval, extraction, and tool-use patterns already in the stack.  │
│                                                                    │
│ Why this week                                                      │
│ Public release with fast adoption across agent tooling workflows.  │
│                                                                    │
│ Adoption cost                                                      │
│ ~2 hours to audit and prototype one skill in an existing agent.    │
│                                                                    │
│ Next action                                                        │
│ Lab one skill inside a LangGraph node and record findings.         │
├────────────────────────────────────────────────────────────────────┤
│ [ 🧪 Run Lab ]  [ 📚 Full evaluation ]  [ 📊 Compare ]              │
└────────────────────────────────────────────────────────────────────┘
```

What the card gives you at a glance:

| Field | Why it matters |
|---|---|
| **Verdict** | ADOPT, TRIAL, ASSESS, or HOLD keeps the discussion decision-oriented. |
| **SOC2 posture** | Safe, conditional, or blocked prevents accidental vendor drift. |
| **Readiness** | A 5-slot meter separates "interesting" from "ready to test." |
| **Why this week** | Explains the trigger, not just the tool. |
| **Next action** | Converts signal into ownership: lab, evaluate, monitor, or hold. |

### Actions and commands

| Surface | Behavior |
|---|---|
| **🧪 Run Lab** | Pulls the open-source tool, generates a synthetic test shaped like the configured stack, runs it in a hermetic subprocess (no app secrets reach the child), and posts insights in the verdict thread within ~5–15 min. Only shown on github.com / pypi.org / huggingface.co / gitlab.com URLs. |
| **📚 Full evaluation** | Runs an on-demand deep verdict and replies in the same thread. |
| **📊 Compare** | Opens a modal showing prior vs current verdict from memory. |
| `/radar TOOL` | Returns the latest verdict for a tool. |
| `/recall TOPIC` | Returns the top semantically related prior verdicts. |

---

## Safety Model

Frontier Scout assumes public web content is hostile until proven otherwise.

| Risk | Control |
|---|---|
| Prompt injection from source text | Source items are wrapped in `source_data` tags, and validators reject known injection signatures. |
| Hallucinated tools or fake URLs | Tool names are fuzzy-matched against input titles; URLs must pass an allowlist before becoming clickable. |
| Incident-as-tool mistakes | Validators reject breach, leak, outage, compromised, and similar incident patterns as tool names. |
| Provider instability | Anthropic calls route through retry/backoff with jitter and quality-log counters. |
| Silent Slack loss | Slack posts retry, dead-letter on exhaustion, and record partial threaded delivery outcomes. |
| Public Lambda endpoint | Every HTTP request must pass Slack HMAC verification with a 5-minute replay window. |
| S3 mirror abuse | Mirror sync guards path traversal and caps object count and total bytes. |
| Secret leakage | `.env` is ignored; detect-secrets runs locally and in PR checks. |

See [`SECURITY.md`](SECURITY.md) for the full threat model, rotation schedule, and operator runbook.

---

## Cost

Observed steady-state spend is tiny enough for a personal project, but explicit enough for a production owner.

| Component | Per run | Per month |
|---|---:|---:|
| Scout | ~$0.30 | ~$1.20 |
| Pulse | ~$0.01 silent / ~$0.10 firing | ~$0.30 |
| Synthesizer | ~$0.10 | ~$0.10 |
| OpenAI embeddings | n/a | ~$0.10 |
| Lambda + S3 | n/a | < $0.10 |
| **Total** | | **~$2/month** |

Every LLM call is logged to `costs.jsonl` with token usage and estimated dollars.

---

## Quickstart

### Local demo

```bash
python scripts/demo.py
open demo/briefing.html
```

### Full local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pre-commit detect-secrets
pre-commit install
cp .env.example .env
```

Fill in `.env`, then run:

```bash
python scripts/preflight.py --skip-aws --skip-lambda
DRY_RUN=1 python scripts/scout.py
DRY_RUN=1 python scripts/pulse.py
pytest tests/test_validators.py tests/test_pipeline_bits.py tests/test_lambda_handler.py -v
```

Live model tests are available when `ANTHROPIC_API_KEY` is set:

```bash
pytest tests/ -m live -v
```

Required for local pipeline runs:

- `ANTHROPIC_API_KEY`
- Optional `OPENAI_API_KEY` for memory/embeddings
- Optional `GITHUB_TOKEN` for higher GitHub rate limits
- Slack target for non-dry-run posting: `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID`, or `SLACK_WEBHOOK_URL`

---

## Production Checklist

Run this once before enabling scheduled pipelines.

1. Configure GitHub Actions credentials: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, Slack credentials, and optional `GH_TOKEN` for Slack-triggered workflows.
2. Run local preflight: `python scripts/preflight.py --skip-aws --skip-lambda`.
3. Run unit tests and live verdict tests.
4. Trigger one manual **Scout** workflow run on `main`. Set `DEBUG=true` for the test run — it bypasses the Mem0 prior-filter (so back-to-back tests don't drain the candidate pool) and skips Mem0 seeding (so test verdicts don't pollute the production memory store).
5. Confirm the Slack post lands, generated artifacts commit back, and `quality-log.jsonl` shows a healthy judge rating.
6. Trigger one manual **Pulse** workflow run.
7. **Set `DEBUG=false` (or unset)** and enable schedules only after the manual Scout and Pulse runs are clean. A loud banner prints at the start of every run when `DEBUG` is on, so it's impossible to miss if accidentally left enabled.

### GitHub Actions schedules

| Pipeline | Cron UTC |
|---|---|
| `scout` | `30 3 * * 1` |
| `pulse` | `30 2 * * *` |
| `synthesizer` | `0 9 1 * *` |
| `cost-report` | `0 12 * * 0` |

### Optional Slack interactivity Lambda

The threaded briefing works without Lambda. Deploy Lambda only for buttons and slash commands.

The Lambda pulls the radar + Mem0 store **directly from GitHub via its REST API
on cold start** — no S3 mirror required. For public repos, the mirror can work
without a token; for private repos or higher rate limits, set `GH_TOKEN`.
Tarball content is cached in `/tmp` for 10 minutes; warm Lambda invocations are
zero-cost.

If you'd prefer the legacy S3-mirror path, set `S3_MIRROR_BUCKET` on the Lambda
and add an `aws s3 sync` step to the GitHub Actions workflow. The code path
auto-detects which mirror is configured.

1. Create a Python 3.11 Lambda with `AWSLambdaBasicExecutionRole`.
2. Build and upload: `bash lambda/deploy.sh`.
3. Enable a Function URL with auth type `NONE`; Slack signs requests and `lambda/slack_verify.py` verifies them.
4. Configure the Slack app:
   - Bot scopes: `commands`, `chat:write`, `chat:write.customize`, `reactions:write`,
     `reactions:read`, `channels:history` *(the last two power the channel
     taste model — reactions feed the bandit and thread replies count as
     engagement signals)*
   - Interactivity URL: Lambda Function URL
   - Event Subscriptions: enable, set Request URL to the same Lambda Function
     URL, subscribe to bot events `reaction_added`, `reaction_removed`,
     `message.channels`. Reinstall the app to grant the new scopes.
   - Slash commands: `/radar` and `/recall`
5. Set Lambda env vars (no AWS env vars needed for the default mirror path):
   - `SLACK_SIGNING_SECRET`
   - `SLACK_BOT_TOKEN`
   - `GH_TOKEN` — GitHub fine-grained token with Actions write and Contents read/write for this repo; used for Slack-triggered workflows and private-repo mirror reads
   - `GH_REPO` — `owner/repo`
   - `GH_BRANCH` — defaults to `main`
   - `SLACK_CHANNEL_ID`
   - `OPENAI_API_KEY` — only if you want semantic `/recall` (the chromadb Lambda Layer is required separately for that to work)
6. Test in Slack with `/radar mem0`, then click one briefing button.

---

## Operations

| Need | Command or file |
|---|---|
| See the product without setup | `python scripts/demo.py && open demo/briefing.html` |
| Preflight before schedules | `python scripts/preflight.py` |
| Trigger Scout manually | GitHub Actions -> Scout -> Run workflow |
| Debug a low-quality run | Last row of `quality-log.jsonl`, then the matching briefing markdown |
| Inspect judge fallback usage | `grep judge_used_fallback quality-log.jsonl` |
| Repost failed Slack delivery | `.scratch/slack-dead-letter.jsonl` |
| Add an RSS source | `scripts/scout.py` `RSS_FEEDS` |
| Add a safe domain | `scripts/validators.py` `ALLOWED_DOMAINS` |
| Update SOC2 rubric | `scripts/prompts.py` `SOC2_RUBRIC` |
| Redeploy Lambda | GitHub Actions `Deploy Lambda` workflow |
| Rotate Slack signing secret | Slack app -> Basic Information -> regenerate -> update Lambda env |

### Repository map

```text
frontier-scout/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── ROADMAP.md
├── SECURITY.md
├── .env.example
├── .github/workflows/
├── tech-radar.md
├── skills-log.md
├── demo/
├── briefings/
├── archive/
├── memory/chroma/
├── costs.jsonl
├── quality-log.jsonl
├── scripts/
│   ├── scout.py
│   ├── pulse.py
│   ├── synthesizer.py
│   ├── judge.py
│   ├── validators.py
│   ├── slack_post.py
│   ├── preflight.py
│   └── demo.py
├── lambda/
│   ├── handler.py
│   ├── slack_verify.py
│   ├── radar_query.py
│   ├── button_dispatch.py
│   └── deploy.sh
└── tests/
```

---

[Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [License](LICENSE)
