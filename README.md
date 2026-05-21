```
   █████╗ ██╗    ████████╗███████╗██╗     ███████╗███╗   ███╗███████╗████████╗██████╗ ██╗   ██╗
  ██╔══██╗██║    ╚══██╔══╝██╔════╝██║     ██╔════╝████╗ ████║██╔════╝╚══██╔══╝██╔══██╗╚██╗ ██╔╝
  ███████║██║       ██║   █████╗  ██║     █████╗  ██╔████╔██║█████╗     ██║   ██████╔╝ ╚████╔╝
  ██╔══██║██║       ██║   ██╔══╝  ██║     ██╔══╝  ██║╚██╔╝██║██╔══╝     ██║   ██╔══██╗  ╚██╔╝
  ██║  ██║██║       ██║   ███████╗███████╗███████╗██║ ╚═╝ ██║███████╗   ██║   ██║  ██║   ██║
  ╚═╝  ╚═╝╚═╝       ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝
```

**Built for AI-native engineering teams**

_A practical adoption radar for AI-native engineering teams._

![python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)
![models](https://img.shields.io/badge/models-Sonnet_4.6_+_Opus_4.7-d97757)
![cost](https://img.shields.io/badge/cost-~%242%2Fmonth-success)
![tests](https://img.shields.io/badge/tests-59%2F59_passing-brightgreen)
![runtime](https://img.shields.io/badge/runtime-Scheduled_CI_+_AWS_Lambda-blueviolet)
![license](https://img.shields.io/badge/license-MIT-blue)

[Demo](#60-second-demo) · [What You Get](#what-you-get) · [Architecture](#architecture) · [Safety](#safety-model) · [Quickstart](#quickstart) · [Roadmap](ROADMAP.md) · [Security](SECURITY.md)

---

Hundreds of AI tools, agent frameworks, model releases, and research drops appear every week. Most are irrelevant to your stack. A few are worth testing before competitors notice them.

**AI Telemetry is an adoption radar for AI-native engineering teams.** It watches the exploding AI ecosystem, filters the noise, judges what matters against your stack and security bar, and turns the best signals into concrete adoption actions: adopt, trial, assess, or hold.

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

## Why AI Telemetry Exists

The goal is simple: give engineering leadership a weekly, evidence-backed view of which AI tools are worth researching, testing, and adopting.

The AI ecosystem is too fast for manual radar meetings and too noisy for raw feeds. A useful engineering radar needs three things at once: early signal, conservative judgment, and a direct path from "interesting" to "someone tested this on a real problem."

AI Telemetry turns public launches, releases, trending repos, newsletters, arXiv papers, HN posts, and HuggingFace movement into a weekly briefing that a real platform team can act on.

### Why not just use...

| Alternative | Where it breaks | What AI Telemetry adds |
|---|---|---|
| **Newsletters** | Great awareness, weak fit to your stack. | Stack-aware verdicts, SOC2 posture, adoption cost, and next actions. |
| **GitHub Trending** | Strong velocity signal, lots of irrelevant repos. | Stratified source caps, judge vetoes, policy gates, and prior-memory filtering. |
| **Manual radar docs** | High quality, low freshness. | Scheduled Scout, daily Pulse, monthly synthesis, and append-only audit logs. |
| **A Slack bot script** | Fun demo, brittle production story. | Retry/backoff, dead letters, secret scanning, preflight checks, and signed Lambda interactivity. |

---

## 60-Second Demo

Run the local demo when you want to understand the product without setting up Slack, AWS, Bitbucket, or API keys.

```bash
git clone https://github.com/YOUR_ORG/ai-telemetry.git
cd ai-telemetry
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
# AI Telemetry — Weekly Briefing · 2026-05-21
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
| `lab-from-slack` | Button click | Markdown lab task in `.scratch/labs/` |
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
S3 mirror -> AWS Lambda Function URL
        |             |
        |             +-> Slack slash commands: /radar, /recall
        |
        +-> Slack buttons: lab, evaluate, compare
                |
                v
        CI custom pipelines
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
│ AI Telemetry — Weekly Briefing · 2026-05-21                       │
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
│ [ Queue lab ]   [ Full evaluation ]   [ Compare history ]          │
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
| **Lab button** | Queues a 30-minute hands-on spike as a markdown task. |
| **Full evaluation button** | Runs an on-demand deep verdict and replies in the same thread. |
| **Compare button** | Opens a modal showing prior vs current verdict from memory. |
| `/radar TOOL` | Returns the latest verdict for a tool. |
| `/recall TOPIC` | Returns the top semantically related prior verdicts. |

---

## Safety Model

AI Telemetry assumes public web content is hostile until proven otherwise.

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

1. Set CI repository variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, `BB_TOKEN`, and Slack credentials.
2. Run local preflight: `python scripts/preflight.py --skip-aws --skip-lambda`.
3. Run unit tests and live verdict tests.
4. Trigger one manual `custom: scout` run on `main`.
5. Confirm the Slack post lands, generated artifacts commit back, and `quality-log.jsonl` shows a healthy judge rating.
6. Trigger one manual `custom: pulse` run.
7. Enable schedules only after the manual Scout and Pulse runs are clean.

### CI schedules

| Pipeline | Cron UTC |
|---|---|
| `scout` | `30 3 * * 1` |
| `pulse` | `30 2 * * *` |
| `synthesizer` | `0 9 1 * *` |
| `cost-report` | `0 12 * * 0` |

### Optional Slack interactivity Lambda

The threaded briefing works without Lambda. Deploy Lambda only for buttons and slash commands.

1. Create the S3 mirror bucket with versioning, encryption, and public access blocked.
2. Create a Python 3.11 Lambda with `AWSLambdaBasicExecutionRole` and read access to the mirror bucket.
3. Build and upload: `bash lambda/deploy.sh`.
4. Enable a Function URL with auth type `NONE`; Slack signs requests and `lambda/slack_verify.py` verifies them.
5. Configure the Slack app:
   - Bot scopes: `commands`, `chat:write`, `chat:write.customize`, `reactions:write`
   - Interactivity URL: Lambda Function URL
   - Slash commands: `/radar` and `/recall`
6. Set Lambda env vars:
   - `SLACK_SIGNING_SECRET`
   - `SLACK_BOT_TOKEN`
   - `BB_TOKEN`
   - `BB_WORKSPACE`
   - `BB_REPO`
   - `SLACK_CHANNEL_ID`
   - `S3_MIRROR_BUCKET`
   - `OPENAI_API_KEY`
7. Test in Slack with `/radar mem0`, then click one briefing button.

---

## Operations

| Need | Command or file |
|---|---|
| See the product without setup | `python scripts/demo.py && open demo/briefing.html` |
| Preflight before schedules | `python scripts/preflight.py` |
| Trigger Scout manually | CI custom pipeline -> `scout` |
| Debug a low-quality run | Last row of `quality-log.jsonl`, then the matching briefing markdown |
| Inspect judge fallback usage | `grep judge_used_fallback quality-log.jsonl` |
| Repost failed Slack delivery | `.scratch/slack-dead-letter.jsonl` |
| Add an RSS source | `scripts/scout.py` `RSS_FEEDS` |
| Add a safe domain | `scripts/validators.py` `ALLOWED_DOMAINS` |
| Update SOC2 rubric | `scripts/prompts.py` `SOC2_RUBRIC` |
| Redeploy Lambda | CI custom pipeline -> `deploy-lambda` |
| Rotate Slack signing secret | Slack app -> Basic Information -> regenerate -> update Lambda env |

### Repository map

```text
ai-telemetry/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── ROADMAP.md
├── SECURITY.md
├── .env.example
├── bitbucket-pipelines.yml
├── tech-radar.md
├── skills-log.md
├── demo/
├── briefings/
├── archive/
├── memory/
├── costs.jsonl          # generated
├── quality-log.jsonl    # generated
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
