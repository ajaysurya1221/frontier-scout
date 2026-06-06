# Frontier Scout Strategy Research for 2026 and 2027

## Executive verdict

Frontier Scout is in the **right strategic neighborhood** after its recent pivot, but it is **not yet on the strongest product line**. The repository has clearly moved away from the broad “AI-adoption radar” story and toward a narrower “sanctioned MCP-server packs” workflow in the README, roadmap, CLI copy, and pivot notes. But the package metadata, release notes, and much of the legacy product surface still describe a broader radar/TUI platform, and the pivot docs explicitly state that the current direction is a **research preview**, not market validation, with **0/5 design-partner sessions completed**. In other words: the project has changed direction conceptually, but it has **not yet earned demand proof or a stable identity**. citeturn36view0turn41view0turn12view1turn28view0turn29view1turn35view0turn40view0

The most promising path is **not** “build a full autonomous SDLC platform,” and it is **not** “replace PMs/designers with AI.” The strongest solo-developer-feasible wedge is a **repo-aware agent governance and interop layer**: Frontier Scout should help teams decide **which agent tools/MCP servers are appropriate for a given repo**, produce **human-reviewable risk evidence**, and **export those decisions into the control planes the team already uses**. The market evidence points to rapidly expanding agentic coding workflows, but it also shows a strong trust gap, growing platform-native governance, and increasing control-plane fragmentation across GitHub, Anthropic, Docker, ServiceNow, Salesforce, and work-management tools. That combination favors a focused governance/translation wedge over a broad platform play. citeturn42search16turn42search12turn42search3turn42search15turn45search19turn45search10turn43search2turn45search1turn43search3turn45search0turn44search2

The blunt answer is this: **Frontier Scout should pivot again, but not radically away from its current pivot**. It should move from **“Claude Code sanctioned MCP packs”** to **“repo-aware AI agent policy compiler and interop layer”**. That is a narrower, more defensible statement of the same core value, and it is materially less obsolete if GitHub, Anthropic, OpenAI, or Docker ship more native agent controls. The product should stop trying to be a broad radar, stop implying a general autonomous-engineering platform, and stop leading with legacy TUI/mission-control surfaces. citeturn36view0turn12view1turn14view0turn45search19turn45search10turn43search2

## What Frontier Scout actually is today

### What is technically real

The real product surface today is much narrower than the full repository might suggest. The implemented core is a CLI path that can **rank MCP candidates for a repo**, present a **static safety summary**, **sanction or unsanction** tools, and **export approved tools into Claude Code managed-config fragments**. The CLI description now leads with sanctioned MCP-server packs; candidate ranking uses a local repo profile plus deterministic fit scoring; the pack flow begins from an offline demo set and can optionally merge live MCP registry entries; and the export path is explicitly limited to Claude Code today. citeturn12view1turn13view2turn15view0turn15view1turn16view0turn21view0turn21view2

The safety model implemented today is also real, but it is narrower than it may first appear. `mcp_audit.py` performs a **static text/schema capability classification** over read, write, network, browser, shell, credential, and unknown capabilities, and it intentionally **fails closed** by marking sparse or empty input as unknown. The exporter writes both a managed settings fragment and a project `.mcp.json`, and it is careful about redacting sensitive text and avoiding credential leakage in generated patterns. Those are concrete, maintainable building blocks. citeturn17view0turn17view1turn18view0turn24view0

The engineering quality is not imaginary. The pivot decision note says the preview was tested at **663 passed / 0 failed**, and the GitHub Actions CI workflow runs linting, type checks, secret scanning, compile checks, coverage, audit, build checks, and non-live tests. The repository also contains a large and mature test suite with coverage across packs, exporters, guard behavior, policies, TUI surfaces, provider selection, dependencies, and incident workflows. That means there is more real software here than the current public traction would suggest. citeturn28view0turn33view0turn8view0

### What is aspirational, stale, or strategically confusing

The repository contains a lot of legacy surface area that is real code but not good product focus. The `frontier_scout/` tree still includes major platform subsystems for authz, context, evals, gateway, memory, observability, orchestration, retrieval, tools, incident-change workflows, a setup wizard, and at least one full Textual TUI stack. The docs and README openly say those radar/TUI/evaluate/guard/report surfaces remain as the “engine underneath,” but the result is still a package that looks substantially broader than the product it should actually be selling. citeturn26view0turn26view1turn26view2turn36view0turn41view0

Several strategically important things are **not built**, even though adjacent language in the repo can make the project feel broader. The pivot docs explicitly say there is **no behavioral sandbox for the sanctioned-pack flow**, **no cross-client export**, **no runtime enforcement**, and **no human-validation claim**. The spike on MCP behavioral probing goes further: today’s sandbox installs packages and runs synthetic scripts, but it **does not speak MCP**, does not support hosted MCP endpoints, and does not persist rich behavioral results into durable receipts. That means any product story that implies real runtime testing of MCP servers is ahead of the code today. citeturn28view0turn38view0turn37view3turn37view2

The repo also has identity drift. The README and roadmap now pitch sanctioned MCP packs, but `pyproject.toml` still describes Frontier Scout as “a local AI adoption radar,” the package version is still `1.8.1`, and `RELEASE_NOTES.md` still describes the project as a local-first AI-tool radar with incident/change and governance slices. That is not a small copy problem; it weakens trust and makes the repository look like it is trying to preserve multiple identities at once. citeturn36view0turn41view0turn35view0turn40view0

### What the repo-fit diagnosis is

Frontier Scout’s strategic assets are clear. The strongest assets are the **repo profiling and fit engine**, the **static MCP/tool capability audit**, the **policy/evidence ledger**, the **sanction/unsanction lifecycle**, and the **config export layer**. Those are precisely the modules you would want if the future product were a repo-aware governance/interoperability layer for AI coding tools. citeturn21view2turn18view0turn15view1turn16view0turn24view0

The biggest distractions are equally clear. Mission Control/TUI depth, BYO-LLM provider handling, broad radar positioning, and Incident Change Scout add maintenance cost and narrative confusion without strengthening the best 2026–2027 wedge. The repo’s own deprecations note effectively admits this: Incident Change Scout is parked, the hard CI guard is demoted to a non-blocking notifier idea, the AI-radar headline is deprecated, and BYO-LLM is no longer a top-level differentiator. citeturn29view0turn36view0turn41view0

External traction is also effectively zero today. The GitHub repository page shows **0 stars, 0 forks, 0 issues**, and the pull-request page shows **1 open pull request**, which is a Dependabot dependency update, alongside 45 closed PRs. That is not condemnation of the code quality, but it is decisive evidence that **there is no outside pull yet**. The repo is an engineering artifact, not a validated market wedge. citeturn19view0turn31view0turn30view0

## What the market is actually buying

### The real state of AI-first organizations

The strong form of the thesis — that companies are broadly replacing PMs, designers, QA, and junior engineers with fully autonomous AI workflows — is **not supported** by the best current evidence. What is supported is a narrower claim: organizations are rapidly adopting AI for software development and workflow automation, but they are doing so in ways that keep **human review, guardrails, and system-of-record integration** at the center. GitHub’s coding agent can research a repo, build an implementation plan, make code changes on a branch, and submit its work via pull requests; OpenAI positions Codex as a coding agent that can write, review, debug, read, edit, and run code across IDE, CLI, web, and CI/CD, including background cloud execution; and Linear now explicitly markets AI workflows shared by humans and agents “from drafting PRDs to pushing PRs.” That is real autonomy, but it is bounded autonomy inside existing engineering systems, not a fully autonomous company. citeturn42search16turn42search12turn42search3turn42search15turn43search1turn43search5

The trust data points in the opposite direction of “full replacement.” Stack Overflow’s 2025 survey says **84%** of developers use or plan to use AI tools, but **46%** actively distrust the accuracy of AI outputs, only **33%** trust them, and only **3%** say they highly trust them. McKinsey’s 2025 survey likewise shows that organizations pursue AI primarily for efficiency, but the high performers are distinguished less by naive automation and more by **workflow redesign**, governance, and pairing efficiency objectives with growth and innovation objectives. That is a strong signal that AI-first organizations are real, but “remove humans from the loop” is not the dominant enterprise buying logic. citeturn45search8turn45search0turn45search12turn44search2

Anthropic’s research further sharpens the picture. In Anthropic’s Economic Index and software-development impact work, software-development requests are among the more specialized, essential AI use cases; the coding agent is associated with more automation; startups are identified as the main early adopters; and UI/UX and simple application-building tasks are among the areas more likely to feel disruption sooner than harder backend or deeply accountable work. That supports a nuanced thesis: **some lower-complexity implementation work compresses first**, especially around scaffolding, interface construction, and repetitive development tasks, but that does not imply broad elimination of product, security, or design ownership. citeturn44search3turn44search7turn44search11

### What is being automated first

The workflows that are most real today are the ones already being built directly into incumbent surfaces. In engineering, that means **issue-to-plan-to-PR** work, repo research, code edits, reviews, and background implementation. In work management, that means **triage, PRD/ticket drafting, and routing work into the engineering system of record**. In design/front-end, that means **prompt-to-UI**, **design-to-code**, and richer design handoff via Figma Dev Mode and adjacent tools. In enterprise operations, that means **agent studios with scoped tasks and guardrails**, as seen in ServiceNow AI Agent Studio and Salesforce Agentforce. citeturn42search16turn42search3turn43search5turn46search0turn46search6turn46search5turn45search1turn43search3

By contrast, the workflows that remain more hype than durable demand are broad, cross-functional “autonomous SDLC” visions that claim to replace planning, implementation, QA, deployment, security review, and continuous improvement in one end-to-end plane. The reason is not only technical; it is organizational. Buyers already have GitHub, Jira, Linear, Figma, deployment systems, security tools, and workspace suites. Any new tool that tries to own the entire chain collides with deeply entrenched platforms and immediately raises trust, accountability, and integration questions. The current market is moving toward **agentized slices inside existing systems**, not toward buying one greenfield suite from a solo developer. citeturn42search16turn42search3turn43search0turn43search1turn46search10turn45search1turn43search3turn45search19

### What is likely to be real by 2027

The most credible 2027 picture is this: AI agents will handle more implementation, more repetitive triage, more test and review assistance, and more tool-mediated work across repos and enterprise systems, but **the control layer becomes more important, not less**. GitHub already supports organization/enterprise MCP registry configuration and server access policy; Anthropic exposes MCP as both protocol and connector surface; the official MCP Registry is now backed by major contributors including Anthropic, GitHub, and Microsoft; and Docker now offers an MCP Catalog and Toolkit for running and managing containerized MCP servers. That is a classic sign that the ecosystem is moving from experimentation to **policy, registry, and runtime standardization**. citeturn45search19turn45search3turn45search10turn45search6turn45search15turn43search2turn43search14

That means the likely budget center in 2026–2027 is not an “AI PM replacement layer.” It is the combination of **coding agents + tool access + governance + evidence + system-of-work integration**. Startups will adopt faster and tolerate more point tooling; enterprises will prefer integrated suites and admin-deployed controls. So the demand opportunity for an independent solo-built product exists, but it exists **between** those suites: not as another runtime, not as another code agent, and not as another work-management platform. citeturn44search11turn45search0turn44search2turn45search19turn43search2turn45search1

### The role-replacement thesis, validated and falsified

The founder’s thesis is **partly right and partly wrong**.

It is right that companies are using AI to compress some labor, especially in implementation-heavy software work. GitHub, OpenAI, Linear, Figma, Vercel, ServiceNow, and Salesforce are all investing in more autonomous agent behavior. Anthropic’s research also suggests earlier disruption risk in simpler UI and application-building tasks. That is real. citeturn42search16turn42search3turn43search1turn46search0turn46search5turn45search1turn43search3turn44search11

It is wrong if interpreted as “buyers want to replace PMs/designers/security reviewers with a third-party autonomous suite.” The strongest evidence says buyers still mistrust outputs, still want guardrails, and still buy inside incumbent systems. Roles are being **augmented and compressed unevenly**, not cleanly replaced. Routine ticket drafting, rote QA, repetitive UI scaffolding, first-pass code reviews, dependency triage, and some support operations are safe to automate first. But prioritization, cross-functional negotiation, architecture ownership, security accountability, brand/design-system stewardship, production approvals, and incident command remain human-owned because the cost of getting them wrong is organizational, not just technical. citeturn45search0turn45search12turn44search2turn46search6turn45search1

## Where incumbents are moving and what they will absorb

### The competitive map that matters

The coding-agent layer is already heavily owned. GitHub owns repo-native planning, branch creation, pull-request flow, and organization-level MCP governance. OpenAI owns a multi-surface coding agent with local and cloud execution, plus skills and MCP connectivity. Anthropic owns Claude Code’s MCP-centered ecosystem and a direct MCP connector in the Claude API. This means Frontier Scout should **not** compete as a coding agent, and it should **not** anchor itself to only one client. citeturn42search16turn45search19turn42search3turn42search15turn42search7turn45search10turn45search6

The work-management layer is also moving fast and is poorly suited to a solo greenfield attack. Linear is explicitly building AI workflows for product development, shared by humans and agents, from PRD drafting to PR creation. Atlassian is embedding Rovo as AI-powered apps across its system-of-work footprint. A standalone tool that mainly drafts tickets, PRDs, or Jira/Linear items is therefore a weak wedge unless it solves a very specific integration/control problem that those systems leave open. citeturn43search1turn43search5turn43search0

The design/front-end layer is crowded as well. Figma AI now includes prompt-to-code and Dev Mode as a design-to-development surface; Vercel v0 is already positioned as a collaborative AI assistant for full-stack web apps. That makes “AI front-end designer/builder” a poor place for Frontier Scout to lead, especially because the repo has no differentiated asset there beyond generic governance instincts. citeturn46search0turn46search6turn46search2turn46search5

The most strategically relevant category for Frontier Scout is the **agent tool governance/runtime/control-plane** layer. GitHub supports organization MCP registries and access-control policies. Anthropic is turning MCP into a first-class connection surface. The official MCP Registry is becoming a centralized metadata layer. Docker’s MCP Toolkit is a beta runtime/catalog surface. ServiceNow and Salesforce are both pushing agent studios and guarded automation. This is where platform-native ownership is emerging — but it is also where fragmentation remains highest across clients, registries, runtime profiles, and approval surfaces. citeturn45search19turn45search3turn45search10turn45search15turn43search2turn45search1turn43search3

### What remains unserved

The gap that still looks open is **repo-aware decision support across multiple control planes**. None of the cited platforms promise the same combined package of: “understand this repo’s stack,” “recommend the least-risk, best-fit tool pack for it,” “show static approval evidence in one place,” and “export the decision into whichever agent control plane the team already uses.” That is an inference, but it is the most important one in this report. The control planes are increasingly native; the **selection, justification, and cross-surface translation** are still fragmented. citeturn45search19turn45search10turn45search15turn43search2turn36view0turn38view1

That gap is narrow enough for a solo developer. It is also narrow enough to survive some native feature absorption. If GitHub improves registry policy, that hurts a pure GitHub-specific exporter but does **not** kill a repo-aware compiler that can target GitHub, Claude Code, Docker, and later other clients. If Anthropic improves managed config, that hurts a pure Claude export tool but not a system that owns the **policy object + evidence object + translation layer**. If Docker owns runtime, that still leaves room for a tool that helps decide **what should be in the approved runtime profile in the first place**. citeturn45search19turn45search10turn43search2

## Best future path for Frontier Scout

### Wedge evaluation

The ten wedges below are scored for **2026–2027 usefulness and demand**, not for how well they preserve the current repo.

| Wedge | Core job-to-be-done | Likely buyer | Solo feasibility | Competitive threat | Repo help | Repo hurt | MVP time | Overall score |
|---|---|---|---:|---|---|---|---|---:|
| **Wedge 8 — ToolHive/Docker/GitHub/Claude interop** | Translate one approved tool policy into multiple agent control planes | Platform lead, AppSec lead, CTO | High | Medium | Strong export, policy, pack, repo-fit assets | Claude-only today; metadata drift | 2–4 weeks | **8.8** |
| **Wedge 3 — MCP Pack Governance** | Recommend and approve repo-fit MCP/tool packs with static risk evidence | Platform/AppSec, AI-first startup CTO | High | Medium | Very strong current fit | Too Claude-centric if left unchanged | 2–4 weeks | **8.5** |
| **Wedge 1 — AI Agent Adoption Firewall** | Approve/test/monitor agent tools before they touch repos, creds, shell, browser | Platform/AppSec | Medium | Medium-high | Policy, audit, ledger, safety framing | “Test/monitor” becomes too big fast | 3–6 weeks if scoped tightly | **7.6** |
| **Wedge 5 — Agent Evaluation and Audit Trail** | Show what was approved, touched, and why | Engineering/security reviewers | Medium | High | Store, receipts, policy findings | Standalone value may be too low | 2–3 weeks | **7.1** |
| **Wedge 4 — AI Work Intake to Jira/Linear** | Turn bugs/goals/incidents into scoped work items for agents | Eng manager, product ops | Medium | High | Some dossier/intake instincts, repo context | Weak product ownership; crowded by Linear/Jira AI | 3–5 weeks | **6.1** |
| **Wedge 7 — AI Front-End Designer/Builder Governance** | Review AI-generated front-end for consistency/accessibility/maintainability | Design systems lead, EM | Medium-low | High | Repo scanner could help with framework fit | No real design-system moat | 4–8 weeks | **5.7** |
| **Wedge 9 — Incident-to-Remediation Agent** | Turn incidents into safe remediation proposals/tickets/PR evidence | SRE lead, platform | Medium | High | Incident Change Scout exists | Different buyer, high trust burden, high complexity | 6–10 weeks | **5.3** |
| **Wedge 2 — Autonomous SDLC Control Plane** | Turn intent into tickets, code, tests, deployment evidence | VP Eng / CTO | Low for solo | Very high | Some repo analysis pieces | Requires huge breadth, heavy integrations | 8–16+ weeks | **4.4** |
| **Wedge 6 — AI Product Manager Replacement Layer** | Replace PRD decomposition/acceptance-checking PM work | Founder, Head of Product | Low | Very high | Very little differentiated asset | Crowded and politically fraught | 6–12+ weeks | **3.8** |
| **Wedge 10 — Kill/pause/OSS-only** | Keep as research OSS and avoid forcing a commercial wedge | Maintainer only | Very high | Low | Honest with current signal | Does not meet usefulness/demand ambition by itself | Immediate | **4.0** |

The wedge rankings are driven by one market reality: **the market is already crowded where language, tickets, design generation, and end-to-end autonomy live; it is less solved where repo-aware governance artifacts must be translated across agent clients and control planes**. That inference follows from the current product expansion of GitHub, OpenAI, Anthropic, Linear, Figma, Docker, ServiceNow, and Salesforce. citeturn42search16turn42search3turn45search10turn43search1turn46search0turn43search2turn45search1turn43search3

### Weighted scoring matrix

The weighted matrix below uses the user’s proposed weighting and scores the **directional candidates**, not every implementation detail. Scores are analytical judgments on a 10-point scale.

| Candidate direction | Market urgency | Growth potential | Willingness to pay | Differentiation | Absorption risk | Solo feasibility | Repo fit | Distribution feasibility | Time to useful MVP | Honesty / safety risk | Weighted total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Repo-aware agent policy compiler + interop** | 8.5 | 8.0 | 7.0 | 8.0 | 6.5 | 8.5 | 8.5 | 7.5 | 8.0 | 9.0 | **7.9** |
| **Local-first agent adoption firewall** | 8.0 | 7.5 | 7.0 | 7.0 | 6.0 | 7.0 | 8.0 | 7.0 | 7.0 | 8.5 | **7.3** |
| **AI work intake for coding agents** | 6.5 | 6.5 | 6.5 | 5.0 | 4.0 | 7.0 | 5.5 | 6.5 | 7.0 | 8.0 | **6.0** |
| **Front-end builder governance** | 5.5 | 6.0 | 6.0 | 4.5 | 4.0 | 5.5 | 4.5 | 5.5 | 5.5 | 8.5 | **5.6** |
| **Incident-to-remediation evidence layer** | 6.0 | 5.5 | 6.5 | 5.0 | 4.0 | 4.5 | 5.0 | 4.5 | 4.5 | 7.5 | **5.2** |
| **OSS-only research tool** | 3.0 | 3.5 | 1.0 | 6.0 | 8.0 | 9.0 | 8.0 | 6.0 | 9.0 | 10.0 | **5.1** |
| **Autonomous SDLC control plane** | 7.5 | 8.5 | 8.5 | 4.0 | 2.5 | 2.0 | 4.5 | 3.0 | 2.0 | 5.5 | **4.7** |
| **AI PM replacement layer** | 4.5 | 5.5 | 5.0 | 3.0 | 2.0 | 3.0 | 3.5 | 4.0 | 4.0 | 5.0 | **4.0** |

The weighted winner is the same as the qualitative winner: **a hybrid of Wedge 3 and Wedge 8**, with a narrow slice of Wedge 1 and Wedge 5 for evidence and drift reporting. That path best matches what the code already does, where platforms are moving, and what a solo developer can realistically ship and maintain. citeturn15view0turn16view0turn24view0turn45search19turn45search10turn43search2

### The product Frontier Scout should become

The best framing is this:

**Frontier Scout should become a repo-aware AI agent policy compiler.**

That means:

- It should take a repo and an organization’s policy preferences.
- It should recommend a **small approved tool pack** for that repo.
- It should attach **human-reviewable static risk evidence**.
- It should let humans **sanction/deny/pin/suppress** tools.
- It should export the result into **multiple existing control planes** rather than owning the runtime itself.

This is a tighter version of the current pivot, not a total reset. It uses the strongest current modules and drops the weakest product-level assumptions. citeturn15view0turn15view1turn24view0turn29view0turn36view0

The **smallest product that could be truly useful in 2026–2027** is:

1. `frontier-scout recommend --repo . --client <target>`  
2. A static approval report that shows **why each tool is recommended or blocked**  
3. `frontier-scout export --target claude-code|github-copilot|docker-mcp-toolkit`  
4. A non-blocking `drift`/`check` command that warns when an approved policy no longer matches the repo or client policy state

Anything broader than that before validation is probably waste. citeturn36view0turn41view0turn45search19turn43search2

### Buyer and ICP analysis

The strongest initial ICPs are not “head of product” or “enterprise transformation office.” They are the people closest to tool approval and day-to-day engineering risk.

| Buyer / ICP | Urgent pain | What they already use | What they would buy | What they would refuse |
|---|---|---|---|---|
| **AI-first startup CTO / founder** | Wants agents to move faster without letting every developer install random tools | Claude Code, Copilot, Cursor, Docker, Linear, Figma | A fast local-first policy compiler that saves time and reduces tool chaos | Another heavyweight admin platform or hosted compliance suite |
| **Platform engineering lead** | Needs approved agent-tool patterns and fewer Slack/Notion debates about “can we use this?” | GitHub, CI, internal standards, IDEs, Docker | Repo-aware approved packs and exportable policy artifacts | A new agent runtime they must operate |
| **AppSec / security engineering lead** | Needs visibility into shell/network/credential-capable tools and human-review evidence | Security review process, GitHub, ticketing, docs | Static evidence, diffs, sanctioned/denied records, drift checks | Any tool that claims “full autonomy” or silently executes tools |
| **Agency / devtools-heavy consultancy** | Needs repeatable approved tool stacks across multiple client repos | Client-specific mixes of IDEs, CI, design tools | Cross-client translation and per-repo approved packs | Client-specific lock-in to one AI vendor |
| **Engineering manager at 20–200 dev org** | Needs bounded autonomy, not chaos | GitHub, Jira/Linear, CI/CD | A clean default approved tool pack and light policy evidence | Another planning/ticketing AI layer |

These ICPs are attractive because the adoption path is short: they can run a CLI on a repo, inspect the artifacts, and compare them to manual config curation. By contrast, PM-replacement, broad SDLC orchestration, and incident-remediation products have longer adoption paths, heavier politics, and much higher trust burdens. citeturn45search19turn43search2turn45search1turn45search0turn44search2

### Anti-obsolescence ranking

The anti-obsolescence test matters more here than usual, because the surrounding platforms are shipping quickly.

| Direction | Obsolescence risk | Why |
|---|---|---|
| **Repo-aware policy compiler + interop** | **Lowest** | Still useful if each platform has its own registry/runtime because it owns the neutral policy model and translation layer |
| **MCP pack governance only** | Low-medium | Useful if it becomes multi-target; risky if it stays Claude-only |
| **Adoption firewall** | Medium | Good if scoped to static preflight and drift; bad if it tries to become a runtime sandbox product |
| **Audit trail only** | Medium-high | Easy for GitHub/OpenAI/Anthropic/ServiceNow to absorb into native history and review surfaces |
| **AI work intake** | High | Atlassian and Linear are already sitting on the system of record |
| **Front-end governance** | High | Figma and Vercel already control most of the relevant context |
| **Incident remediation** | Very high | Platform cloud, observability, and incident vendors can absorb it faster than a solo tool |
| **Autonomous SDLC control plane** | Extreme | The whole market is trying to absorb this into suites and coding platforms |
| **AI PM replacement** | Extreme | Weak trust, weak wedge, high political resistance, high incumbent overlap |

The obsolescence lesson is simple: Frontier Scout should own **decision compilation**, not the full experience around coding, work management, or runtime. citeturn45search19turn45search10turn43search2turn43search1turn46search0turn46search5

## Roadmap and operating rules

### Next 7 days

The next week should be about **product narrowing**, not feature sprawl.

| Move | What to do | Why |
|---|---|---|
| **Rewrite the product identity** | Update `pyproject.toml`, `RELEASE_NOTES.md`, README, CLI help, and roadmap so they all describe the same product | Today the repo tells multiple stories at once, which weakens trust citeturn35view0turn40view0turn36view0turn41view0 |
| **Deprecate the broad radar from the opening surface** | Keep legacy commands, but move Mission Control/radar/BYO-LLM below the fold and under `legacy` or `engine` framing | The repo itself already says those are the engine underneath, not the product citeturn36view0turn29view0 |
| **Define a neutral policy object** | Create a first-class internal schema for `approved`, `denied`, `pinned`, `requires-review`, plus evidence and client targets | This is the core asset that can survive client changes |
| **Build the second export target** | Do **one** of: GitHub MCP registry/server-access export or Docker MCP Toolkit profile export | Without a second export target, Frontier Scout is a client-specific feature, not a product citeturn45search19turn43search2 |
| **Add drift checking** | Non-blocking local/CI command that compares sanctioned policy to exported artifacts and repo signals | This extends the current evidence/policy story without becoming a runtime |
| **Park distractions harder** | Hide Incident Change Scout and TUI from the hero narrative entirely | The repo’s own deprecation note already points this way citeturn29view0 |

What to **show publicly** in the next 7 days: one crisp README demo, one side-by-side export comparison, one markdown approval report, one three-minute demo video.

What signal to collect: “Would you use this instead of manually curating configs or writing internal docs?” Not stars. Not compliments. Not screenshot praise.

### Next 30 days

The next month should produce a **useful product artifact**, not a bigger framework.

| Build | Scope |
|---|---|
| **Policy compiler core** | Neutral internal decision model; import curated MCP metadata; repo-fit ranking; static risk evidence |
| **Two export targets** | Claude Code plus one of GitHub MCP policy or Docker MCP Toolkit |
| **Human-review artifacts** | Markdown + JSON + optional HTML approval bundle, with diffable sanctioned/denied decisions |
| **Drift warnings** | Non-blocking CI/local command for policy drift or unsupported client mappings |
| **Three realistic demos** | One frontend repo, one backend/service repo, one monorepo |
| **Interview kit** | 5 async interview prompts and a structured ledger for “Would this replace your manual process?” |

What **not** to do in the next 30 days:

- do not build a hosted SaaS control plane
- do not build a general agent runtime
- do not build behavioral MCP sandboxing unless a user specifically says static evidence is insufficient
- do not build Jira/Linear integrations yet
- do not build PM-replacement layers
- do not expand the TUI
- do not market “enterprise governance” as if you have enterprise proof

Those non-goals are fully consistent with the repo’s own research-preview and demand-gating language. citeturn28view0turn41view0

### Evidence ladder

The product should only earn bigger claims when it climbs this ladder.

| Level | What counts | What does not count | What it permits | What it does not permit |
|---|---|---|---|---|
| **Level 0** | Internal reasoning | Personal conviction | Prototyping | Product thesis certainty |
| **Level 1** | Repo coherence, passing tests, working export | “It feels solid” | Shipping a preview | Claiming demand |
| **Level 2** | Ecosystem evidence from official docs, surveys, platform launches | General AI hype | Strategic narrowing | PMF language |
| **Level 3** | Passive OSS/public signal: stars, comments, demo interest | Social praise without workflow context | Prioritization hints | Build commitment |
| **Level 4** | Active async feedback from real target users | Friends saying “cool” | Narrower wedge choice | Revenue assumptions |
| **Level 5** | Real workflow trial on a real repo/process | Synthetic testing | Demand-gated build step | Scaling claims |
| **Level 6** | Repeated use over time | One-off trial | Stronger product investment | Broad category claims |
| **Level 7** | Paid commitment or contracted pilot | “We’d probably pay” | Commercial acceleration | None of the above shortcuts |

Frontier Scout is currently somewhere between **Level 1 and Level 2**: there is technical substance and ecosystem logic, but essentially no external demand evidence. The repo’s own validation docs agree. citeturn28view0turn29view1

### Positioning candidates

The top five positioning options below are ranked by usefulness, demand, and anti-obsolescence.

| Rank | Positioning | One-sentence tagline | Best buyer |
|---|---|---|---|
| **1** | **Repo-aware agent policy compiler** | **Compile repo context into approved agent-tool policy.** | Platform lead / AppSec / CTO |
| **2** | **Approved MCP packs for coding agents** | **Choose the right MCP tools for this repo, then export them safely.** | CTO / platform lead |
| **3** | **AI agent adoption firewall for engineering** | **Approve agent tools before they touch code, credentials, or shell.** | AppSec / security engineering |
| **4** | **Agent governance evidence layer** | **Show what your coding agents are allowed to use, and why.** | Security review / engineering leadership |
| **5** | **Agent-safe work intake** | **Turn messy engineering work into tasks agents can execute safely.** | EM / product ops |

The first two are strongest because they align with current repo strengths, avoid direct fights with GitHub/OpenAI/Linear/Figma, and describe a job that is becoming more urgent as registries and runtimes proliferate. citeturn45search19turn45search15turn43search2turn43search1

Below are the most viable README-hero options.

### Candidate one

**Tagline:** Compile repo context into approved agent-tool policy.

**README hero copy:**  
Frontier Scout helps AI-first engineering teams decide **which agent tools are safe and useful for this repo**. It ranks candidate MCP servers and related tool surfaces against your codebase, generates static review evidence, and turns the result into an approved policy bundle your team can actually deploy.

It does **not** run your production runtime, replace GitHub, or replace your work-management stack. It sits above those systems and compiles one reviewable decision into the control planes you already use.

**Why now:** agentic coding is becoming mainstream, while platform-native registry, policy, and runtime surfaces are fragmenting across GitHub, Anthropic, Docker, and adjacent ecosystems. citeturn42search16turn42search3turn45search10turn45search19turn43search2turn45search15

### Candidate two

**Tagline:** Choose the right MCP tools for this repo, then export them safely.

**README hero copy:**  
Registries tell you what exists. Frontier Scout tells you **what belongs here**. It recommends repo-fit MCP/tool packs, shows static capability and policy evidence, and exports those decisions into the control plane your coding team already trusts.

Built for teams that want coding agents without random tool sprawl. Local-first by default. No code upload required.

**Why not GitHub/Anthropic:** because each platform governs its own surface; Frontier Scout owns the repo-aware recommendation and translation layer across them. citeturn45search19turn45search10turn43search2

### Candidate three

**Tagline:** Approve agent tools before they touch code, credentials, or shell.

**README hero copy:**  
Frontier Scout is a lightweight adoption firewall for engineering-side AI agents. It helps platform and security leads review tool capability surfaces, sanction or deny them, and generate diffable approval artifacts.

It is not a SOC2 platform, not a runtime sandbox product, and not an “AI governance suite.” It is the thin layer that removes approval chaos from agent-tool adoption.

**Why now:** trust in AI outputs remains low even as usage rises, which creates pressure for bounded autonomy with reviewable controls. citeturn45search0turn45search8turn44search2

### Candidate four

**Tagline:** Show what your coding agents are allowed to use, and why.

**README hero copy:**  
Frontier Scout records the evidence behind agent-tool approvals. For every sanctioned or denied server, it can preserve repo fit, static risk clues, policy findings, and exported artifacts.

Teams do not need another chat UI. They need a clean approval trail that survives audits, handoffs, and platform churn.

**Why not build this alone:** as a standalone product this is weaker than policy compilation, because native platforms can absorb history and review surfaces quickly. It works best as part of the primary wedge. citeturn42search16turn45search19turn45search10

### Candidate five

**Tagline:** Turn messy engineering work into tasks agents can execute safely.

**README hero copy:**  
Frontier Scout converts rough engineering intent into bounded work packages for coding agents, with explicit constraints, approval criteria, and implementation evidence.

This is attractive, but it should only be built if repeated users tell you the real bottleneck is work intake rather than tool governance itself.

**What this is not:** a PM replacement system. Linear and Atlassian are already pushing AI deeply into planning and delivery. citeturn43search1turn43search5turn43search0

### Distribution strategy

A solo-developer distribution plan should look for **workflow-shaped pull**, not vanity metrics.

| Channel | Exact audience | Exact message | Expected signal | How not to overcount | Success | Failure |
|---|---|---|---|---|---|---|
| **GitHub README + issues** | Engineers already evaluating the repo | “Approved agent-tool packs and policy export for real repos” | Export-target requests, example repos, workflow questions | Stars alone do not count | Two repeated export requests | Zero concrete usage questions |
| **Show HN** | AI coding/tooling early adopters | “Repo-aware approved MCP packs, not another coding agent” | Comments describing real approval pain | Ignore general AI hype comments | 3+ users describe current manual process | Pure “cool demo” responses |
| **Reddit / MCP communities** | Power users experimenting with Claude/Copilot/Docker | “How do you currently approve MCP tools for your team?” | Manual-process stories | Ignore setup curiosity without workflow detail | People volunteer their current process | Thread becomes generic MCP chatter |
| **X / LinkedIn technical posts** | Platform, AppSec, devtools people | “The hard part is no longer finding MCP tools; it is approving and exporting them safely” | Replies from leads, not hobbyists | Ignore likes/bookmarks | 5–10 relevant conversations | Mostly founder-to-founder engagement |
| **Direct async outreach** | CTOs, platform leads, agencies | “Can I compare your manual MCP/tool approval process to a generated one-page artifact?” | Willingness to share a repo/process | Ignore polite declines | 5 real sessions booked | No replies or only praise |
| **Demo video** | Busy technical evaluators | Show input repo → ranked tools → approval evidence → export diff | Completion and follow-up questions | Views do not count | Viewers ask for a target export or sample repo | High views, no follow-up |
| **Devtools/security newsletters** | Governance-oriented practitioners | “Repo-aware agent policy compiler” | Inbound requests from platform/security practitioners | Ignore generic traffic spikes | One serious design-partner lead | Zero qualified replies |
| **GitHub Discussions** | Existing repo visitors | “What target should Frontier Scout export to next?” | Prioritized next export target | Ignore single-voter polls | Two independent asks for same target | Fragmented requests with no pattern |

### What not to build

Do **not** build the following unless external evidence forces it:

- a general autonomous SDLC platform
- an AI PM replacement layer
- a hosted multi-tenant governance SaaS
- a general agent runtime or sandbox farm
- deep Jira/Linear/Slack/ServiceNow/Salesforce integrations at this stage
- a security/compliance marketing layer you cannot honestly support
- cross-client exporters for every vendor at once
- a behavioral MCP probe before users prove static evidence is insufficient
- more TUI complexity
- any claim that Frontier Scout “enforces” policy in production today

The repo’s own research-preview language already points toward this level of restraint; the market data makes that restraint even more important. citeturn28view0turn41view0turn45search19turn43search2

### Continue, pause, pivot, and kill criteria

| Decision | Rule |
|---|---|
| **Continue** | At least 3 of 5 real target users say the generated policy/evidence bundle is better than manual config/wiki/Slack curation |
| **Pivot within the wedge** | Users like the evidence but keep asking for a different export/control-plane target |
| **Pause** | After 5 real conversations, no one wants to route an artifact through a real process |
| **Kill the commercial thesis** | After 30 days, no repeated workflow pull appears and platform-native controls eliminate the translation gap |
| **Release more visibly** | The second export target works, the README is coherent, and 3 demo repos are stable |
| **Seek users aggressively** | Once the product identity is narrowed and the artifact is opinionated enough to compare against manual practice |
| **Stop coding temporarily** | If signals remain at Levels 1–3 only; spend time recruiting users instead of adding capabilities |

## Final recommendation

Frontier Scout should become a **repo-aware AI agent policy compiler and control-plane interop layer**.

It should stop being a broad “AI-adoption radar,” stop acting like an incipient autonomous SDLC suite, and stop leading with legacy TUI/mission-control surfaces. It should keep the repo-aware ranking engine, static capability audit, policy findings, sanction lifecycle, and export architecture — and build exactly one thing on top of them: a **small, reviewable, exportable policy object for AI coding tools**. citeturn36view0turn41view0turn29view0turn15view0turn24view0

The strongest wedge is a hybrid of **Wedge 3 and Wedge 8**: **MCP/tool pack governance plus interop into existing agent control planes**. If you want a simpler naming statement, call it an **AI Agent Adoption Firewall for repos**, but make the actual implementation about **recommendation + sanction + export**, not about building a runtime or claiming deep behavioral enforcement. citeturn45search19turn45search10turn43search2turn36view0

The riskiest assumption is this: **that teams will want a third-party repo-aware policy/evidence layer on top of GitHub/Anthropic/Docker native controls instead of just using those native controls directly**. That assumption is plausible because the ecosystem is fragmented, but it is not yet proved. This is the one thing the next 30 days must test. citeturn45search19turn45search10turn43search2turn45search15

The first concrete action is to **ship a second export target and rewrite the repository around one identity**. Until Frontier Scout targets more than Claude Code, it is too easy for buyers to treat it as a neat Claude-specific side utility rather than a serious layer in the agent-governance stack. citeturn14view0turn36view0turn35view0

The next thing to ask Claude Code or Codex to do is:

```text
Refactor Frontier Scout into a repo-aware agent policy compiler.

Goals:
1. Make sanctioned packs the only primary product surface.
2. Introduce a neutral internal policy object for approved/denied/pinned tools plus evidence.
3. Keep existing Claude export.
4. Add one new export target: GitHub MCP policy OR Docker MCP Toolkit profile.
5. Add a non-blocking `drift` command that compares the sanctioned policy to exported artifacts.
6. Move Mission Control, broad radar, and Incident Change Scout behind legacy/experimental framing in help text and README.
7. Update pyproject metadata, release notes, roadmap, and README so they all describe the same product.
8. Add snapshot tests for both export targets and for the approval report artifact.
9. Preserve backwards compatibility for existing commands where practical, but remove them from the main narrative.
10. Produce a concise migration note in DEPRECATIONS.md and CHANGELOG.md.
```

The things to research again in 30 days are not broad market categories; they are very specific moving surfaces:

- GitHub’s MCP registry and server-access policy evolution
- Anthropic’s Claude Code managed config and MCP connector changes
- Docker MCP Toolkit’s progress from beta
- whether Cursor/Windsurf publish serious organization-level policy surfaces
- whether users keep the **evidence artifact**, the **export artifact**, or both
- whether real users ask for **GitHub export**, **Docker export**, or **ticket/work-intake** more often
- whether any design partner actually routes the output through a real approval process

The shortest honest summary is this:

**Frontier Scout is not dead. It should not be killed today. But it should pivot from “sanctioned MCP packs for Claude Code” to “repo-aware agent policy compiler and interop,” and it should prove that wedge with real users before building anything broader.**