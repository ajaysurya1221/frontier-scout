# Personalized AI Adoption Intelligence

Frontier Scout's strongest wedge is personalized scouting first, with
try-before-trust as the safety engine.

The product loop is:

```bash
frontier-scout profile --repo .
frontier-scout scan --repo .
frontier-scout dossier <tool>
frontier-scout trial <tool> --sandbox local
frontier-scout guard --repo .
```

## Product Thesis

Developers do not need another generic AI directory. They need a local system
that watches the AI-tool ecosystem, understands enough about their repos to
rank what matters, and then forces evidence before adoption.

Frontier Scout should answer:

- What new or trending AI tools matter for this repo?
- Which problem could this tool solve here?
- What permission surface does it introduce?
- What is still unknown?
- What is the smallest safe trial?

## Ideas Absorbed

| Reference | Useful idea | Frontier Scout interpretation |
|---|---|---|
| OpenClaw | Local ownership and guided onboarding | Make repo profiling feel like owning your scout, not feeding SaaS telemetry. |
| GBrain | Answer plus gap analysis, not search results | Dossiers include explicit unknowns and missing evidence. |
| Understand Anything | Durable local understanding artifacts | Scout Profile and Scout Graph are local adoption artifacts, not visual novelty. |
| Mastra / LangGraph | Durable workflows, HITL, observability | Scout and trial pipelines should be resumable and approval-aware over time. |
| Ralph Loop | Long-running work in sandboxes | Future toolbench runs bounded recipes inside isolated backends. |
| bolt.diy / awesome-llm-apps | Runnable next steps | Every recommendation should include a safe next command or recipe. |
| MCP ecosystem | Tool interoperability creates permission risk | MCP capability audit is a first-class scout primitive. |
| shadcn/ui | Own the code and artifacts | Receipts, profiles, policies, and probes stay local and inspectable. |

## Current Slice

The current implementation adds:

- `frontier-scout profile --repo .` for a local Scout Profile.
- Personalized dry-run scan annotations: fit reasons, unknowns, and next safe
  steps.
- `frontier-scout dossier <tool>` for a local adoption dossier.
- `frontier-scout trial --sandbox local|report-only` compatibility over the
  existing lab/dry-run safety model.

The implementation deliberately does not become another agent framework,
workflow builder, graph dashboard, SaaS directory, or sandbox provider.

## Next Build Direction

The next meaningful release should make the radar living instead of static:

- connect repo profiles to verdicts, tools, permissions, trials, and decisions,
- add Living Scout Packs whose seeds can be promoted, demoted, and retired,
- add dependency intelligence for meaningful security, hardening, and breaking
  releases that affect this repo,
- surface capability drift: current choices that are getting stale and stronger
  alternatives worth trialing,
- add a bounded Sandbox Toolbench backend for local Docker and optional E2B-like
  providers.

## v0.2 Living Radar

Curated seed repos are bootloaders, not permanent truth. v0.2 treats packs as
local graph tags over tools. A candidate can enter through GitHub, PyPI, npm,
Hugging Face, HN/RSS, or an MCP registry signal, then move through:

```text
candidate -> watched -> core -> retired
```

Promotion requires repeated evidence from independent source families. A single
viral spike can surface an `ASSESS` item, but it cannot create an `ADOPT`
recommendation.

Dependency intelligence keeps the same posture. Frontier Scout is not a package
manager or Dependabot clone. It detects repo-relevant upgrades such as a
hardening release for `langchain-core`, explains why the change matters here,
and emits a safe trial recipe instead of editing manifests.
