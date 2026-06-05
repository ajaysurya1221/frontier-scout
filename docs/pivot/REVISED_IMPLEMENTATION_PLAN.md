# Revised Implementation Plan — Frontier Scout pivot to "Sanctioned MCP-server packs"

Sources of truth: **follow-up research** (`traction_research/research_2.pdf`, highest priority) ·
original research (`traction_research/Frontier Scout decision brief.pdf`, supporting) · the repo
(technical feasibility). This plan is the v3, post-adversarial plan; three load-bearing technical
claims were verified against the code (cited inline).

---

## 1. What changed because of the follow-up research

The follow-up pre-mortem stress-tested the prior plan (a GitHub-Action + CI-guard + "trial receipt"
intake gate) and ruled: **keep the problem, rewrite the execution wedge.** Market controls are
moving **upstream** — install-time allowlists, managed MCP configs, curated catalogs, sandboxed
runtime (GitHub MCP Registry, Claude Code managed config, Docker MCP Toolkit, Stacklok ToolHive,
Socket). The prior plan put its control point **downstream** at CI/merge, *after* the real
install/approve decision already happened in the client.

- **Direction:** wedge moves to install/approval time. "GitHub Action first" / CI receipt is a red line.
- **Positioning:** one job — *"approve & operationalize MCP servers safely for enterprise coding assistants."* Kill the broad "AI-tool radar"; demote BYO-LLM.
- **Proof:** mandatory universal receipts are a red line; the verification-gap study (arxiv 2605.14675) supports **human-approved evidence for selected high-risk tools only**, not a universal ritual.
- **Pain/urgency:** 84% use/plan AI tools; 50.6% daily; only 2.7% "highly trust" output; 81% have agent security concerns; 38% have no agent plans → friction is fatal; over-strict governance drives shadow usage (Gartner/TechRadar).
- **Verified technical correction (biggest):** the repo sandbox **cannot trial an MCP server** —
  `scripts/lab_runner.py` only installs a package + runs a synthetic "does it import?" script; no
  MCP-protocol behavior exists; a package-less/remote server produces no trial; behavioral insight
  is discarded at the process boundary (`trials.py:66`). So **behavioral sandbox evidence is
  net-new (V1, gated)**, and the MVP proof is a **static** capability+policy safety map. (See
  `docs/spike-mcp-probe.md`.)
- **Exporter target corrected:** the surface that governs the real risk (user-scoped
  `~/.claude.json`) is the **managed** `allowedMcpServers`/`deniedMcpServers` + `managed-mcp.json`
  (admin/MDM-deployed) — verified against live docs (`docs/spike-claude-config.md`).

## 2. What from the old plan is kept

- The problem + local-first invariants (no source to LLM, local-first, no telemetry, hermetic labs, `.tcss`-in-wheel, tag-push release).
- The repo-aware ranking **engine** (`profile`→`stack`→`evaluate._fit`/`scout._personal_fit`), re-roled from "the product" to "the ranking engine behind the product."
- Parking Incident Change Scout (the follow-up research explicitly agrees).
- The offline/keyless demo path — now the substrate for the validation pack flow.
- The permission-audit (`mcp_audit`) and policy (`policy`) engines; reuse-not-rebuild for `packs`/`store`.
- Phase-0 safety discipline (branch, recorded baseline, deprecation-not-deletion).

## 3. What from the old plan is modified

- Headline verb: `intake <url>` → pack-centric `packs candidates / sanction / export`.
- Output artifact: decision-card + CI check → **control-plane export** (managed config primary).
- "Receipt" → **static safety summary** by default (behavioral evidence = V1, high-risk only).
- `guard`: hard CI gate → optional **non-blocking notifier**.
- `packs.py`: a "feed" → the **center** of the product.

## 4. What from the old plan is removed

- GitHub-Action-as-MVP; hard blocking CI guard; mandatory universal receipts; the broad "AI-tool radar" category framing; the **Backstage** exporter (replaced by Claude/GitHub/Docker control planes); the v2 `intake.py`/`intake_decisions` table; **any claim that behavioral sandbox evidence is MVP-cheap reuse.**

## 5. Final product thesis

*MCP-server adoption in coding assistants is fast, local, and distrusted. Frontier Scout gives a
platform/AppSec lead a **repo-ranked, sanctioned set of approved MCP servers** for their team's
assistant (Claude Code first), plus a **one-step export into the managed config they already
control** — coexisting with GitHub/Anthropic/Docker/ToolHive rather than out-governing them. A
static capability+policy safety map is the MVP proof; behavioral sandbox evidence is added only if
validation pulls, and only for high-risk servers.*

- **User:** platform-eng / AppSec lead at a GitHub-heavy org whose devs use Claude Code; today answers "can we use this server?" via Slack/wiki/hand-edited `.mcp.json`.
- **Differentiation:** repo-aware prioritization + static risk map + **cross-client sanctioned export**. Not "we secure packages" (Socket); not "we run the runtime" (ToolHive/Docker).
- **Validation signals:** (1) ≥3/5 users prefer the pack to hand-curating `.mcp.json`/Slack; (2) users voluntarily keep the safety summary; (3) ≥1 team would route the export through their process.

## 6. Final MVP scope

**MVP (CLI only — the 2-week validation artifact):**
1. `packs candidates --repo . --client claude-code` — `mcp`-pack servers, registry-enriched, **repo-ranked**.
2. **Static safety map** per server — `mcp_audit` capabilities + `policy` read (labeled "static analysis").
3. **Risk-gated sanction** — low-risk → `packs sanction`; high-risk (`dangerous_flags ∈ {write,shell,credential,network}`) → must show a safety summary first.
4. `packs export --client claude-code` — managed `allowedMcpServers`/`deniedMcpServers` (primary) + project `.mcp.json` (secondary).
5. **Offline demo pack** (5–10 seeded servers) — keyless full loop.
6. **Repositioned copy.**

**V1 (demand-gated):** behavioral MCP probe (new `mcp` dep, high-risk only); Copilot + GitHub allow-list exporter; Docker catalog; non-blocking notifier; interactive TUI flow.
**Non-goals now:** blocking CI guard; GitHub-Action-as-primary; broad radar; Backstage; deep IDE plugin; hosted telemetry/accounts/billing.

## 7. Implementation phases

- **Phase 0 — Safety, baseline, alignment, spikes:** branch, recorded baseline, `DEPRECATIONS.md`, copy reposition, Spike A (`docs/spike-mcp-probe.md`), Spike B (`docs/spike-claude-config.md` + fixtures). *No feature code.*
- **Phase 1 — Pivot foundation:** `"sanctioned"` state + CHECK migration; enrich `PackCandidate` + registry parser; ranker adapter + repo-ranked candidates; overrides reader + extended `adoption_decisions`; static safety-summary renderer.
- **Phase 2 — MVP journey:** managed-config exporter; CLI `packs candidates/sanction/export` (risk-gated) + offline demo pack + e2e.
- **Phase 3 — Instrumentation & validation:** opt-in telemetry + `stats`; A/B/C proof harness; `docs/validation-protocol.md` (thresholds + kill criteria).
- **Phase 4 — Launch / V1-gated:** park ICS behind a flag; non-blocking notifier; harden exporter; document V1-gated builds awaiting validation.

## 8–11. Task cards (with TDD requirement, verification command, acceptance criteria)

> Repo test command: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -m "not live" -q`

**P0-1 Branch + baseline + deprecation notices** — Phase 0.
- TDD: N/A (git + markdown, no behavior). Verify: baseline suite recorded (`600 passed, 3 env-only fails`). Accept: branch `pivot/sanctioned-packs`; `DEPRECATIONS.md` + `CHANGELOG.md` notices, not deletions.

**P0-2 Reposition headline copy** — Phase 0.
- TDD: not meaningful (copy/help strings). Verify: `frontier-scout demo --no-serve && git diff --exit-code -- demo/`; `frontier-scout --help`; `python -m build`. Accept: README/CLI lead with "sanctioned MCP packs"; radar/BYO-LLM demoted; no behavior change.

**P0-3 Spike A (MCP-probe feasibility)** — Phase 0.
- TDD: N/A (read-only doc). Verify: `docs/spike-mcp-probe.md` cites real `lab_runner.py` refs. Accept: costed build-vs-defer recommendation; probe scoped high-risk-only/V1.

**P0-4 Spike B (Claude config fixtures)** — Phase 0.
- TDD: light (data) — red loader test asserts each fixture is valid JSON of the documented shape. Verify: `pytest tests/test_claude_config_fixtures.py -q`. Accept: `tests/fixtures/claude_config_{managed,project}.json` match live docs; managed-vs-user-scoped reach noted.

**P1-1 `"sanctioned"` state + CHECK migration** — Phase 1. Files: `packs.py`, `store.py`, `tests/test_store_migration.py`.
- TDD: REQUIRED — red `test_store_migration` (CHECK accepts "sanctioned"; rows preserved; `init_db` idempotent ×2). Verify: `pytest tests/test_store_migration.py -q`. Accept: migration via table-rebuild; back up `db.sqlite`; stamp next version.

**P1-2 Enrich `PackCandidate` + registry parser** — Phase 1. Files: `packs.py`, `tests/test_packs_registry.py`.
- TDD: REQUIRED — red: parse a fixture registry payload → populated `category`/`description`/`tags`/`server_meta`. Verify: `pytest tests/test_packs_registry.py -q`. Accept: offline (`discover=False`) characterization unchanged; fail-closed on bad data.

**P1-3 Ranker adapter + repo-ranked candidates** — Phase 1. Files: `evaluate.py`/`scout.py`, `packs.py`, `tests/test_packs_ranking.py`. Depends: P1-2.
- TDD: REQUIRED — red: MCP-relevant servers rank above unrelated for a `.claude` repo; characterization pins scan-path output unchanged. Verify: `pytest tests/test_packs_ranking.py -q`. Accept: deterministic/offline; public `rank_candidates_for_repo` wrapper (no private leakage); `candidate_rows_for_pack(profile=None)` back-compat.

**P1-4 Overrides reader + extended `adoption_decisions`** — Phase 1. Files: `store.py`, `tests/test_overrides_enforcement.py`.
- TDD: REQUIRED — red: exclude removes, pin reorders, sanction row round-trips with pack+client. Verify: `pytest tests/test_overrides_enforcement.py -q`. Accept: `adoption_decisions` +`pack_slug`+`client` + `save/list`; `list_pack_overrides` + precedence (exclude>pin>include).

**P1-5 Static safety-summary renderer** — Phase 1. Files: `frontier_scout/safety_summary.py`, `tests/test_safety_summary.py`.
- TDD: REQUIRED — red: summary asserts capability+policy lines, "static analysis" label, planted-secret redaction. Verify: `pytest tests/test_safety_summary.py -q`. Accept: renders offline keyless; no "we ran it" framing; redacts via `sanitize_sensitive_text`.

**P2-1 Managed-config exporter** — Phase 2. Files: `frontier_scout/exporters/{__init__,claude_config}.py`, `tests/test_exporters_claude.py`.
- TDD: REQUIRED — red: managed + project fragments match Spike-B fixtures; unsanctioned→`deniedMcpServers`; secrets redacted. Verify: `pytest tests/test_exporters_claude.py -q`. Accept: managed (primary) + project (secondary) faces; valid JSON of the documented shape.

**P2-2 `packs candidates --repo --client`** — Phase 2. Files: `cli.py`, `tests/test_packs_candidates_cli.py`.
- TDD: REQUIRED — red: CLI invocation ranks + filters by client + runs offline. Verify: `pytest tests/test_packs_candidates_cli.py -q`. Accept: house `--json` style; `client_scope` filter.

**P2-3 `packs sanction/unsanction` (risk-gated)** — Phase 2. Files: `cli.py`, `packs.py`, `tests/test_sanction_gating.py`.
- TDD: REQUIRED — red: high-risk blocks sanction without a summary; low-risk passes; row persisted. Verify: `pytest tests/test_sanction_gating.py -q`. Accept: writes `adoption_decisions`; gate uses `mcp_audit.dangerous_flags`.

**P2-4 `packs export` + offline demo pack + e2e** — Phase 2. Files: `cli.py`, `packs.py` (seed), `tests/test_pack_flow_e2e.py`.
- TDD: REQUIRED (e2e) — red: candidates→safety→sanction→export round-trips a valid config offline, HOME-isolated. Verify: `pytest tests/test_pack_flow_e2e.py -q`; then `frontier-scout packs candidates --repo . --client claude-code --json` + `… export --client claude-code --target /tmp/mcp.json`. Accept: full loop offline; 5–10-server demo pack; no `git diff` pollution.

**P3-1 Telemetry + `stats`** — Phase 3. Files: `packs.py`/`safety_summary.py`, `platform/observability/*`, `cli.py`, `tests/test_pack_telemetry.py`.
- TDD: REQUIRED — red: events append only when opted-in (off by default); zero-egress assertion; `stats` aggregates a scripted run. Verify: `pytest tests/test_pack_telemetry.py -q`. Accept: local `pack-events.jsonl`; `AuditRecord` wired; no network.

**P3-2 A/B/C proof harness + validation protocol** — Phase 3. Files: `safety_summary.py`, `docs/validation-protocol.md`, `tests/test_proof_variants.py`.
- TDD: REQUIRED for render (red: 3 variants render + preference captured); protocol doc = docs (review/build). Verify: `pytest tests/test_proof_variants.py -q`. Accept: approval-only/static-summary/formal-receipt variants; protocol has 3 thresholds + baseline + kill criteria.

**P4-1 Park ICS + non-blocking notifier + harden + gated stubs** — Phase 4. Files: `platform/incident_change_scout/*`, `guard.py`, `exporters/*`, packaging.
- TDD: REQUIRED for behavior (red tests for notifier mode + flag gating); docs/release via `python -m build` + `.tcss` wheel smoke. Verify: full suite + wheel check. Accept: `incident` behind experimental flag; non-blocking `notify` mode; V1-gated builds documented as awaiting Phase-3 validation.

## 12. Assumptions & confidence

| # | Assumption | Conf. | If wrong |
|---|---|---|---|
| A1 | Keep problem, install-time pack wedge | High | re-scope to narrowest pulled sub-problem |
| A2 | Static safety map is enough to start (behavioral deferred) | Medium | build the probe sooner (P0-3 cost in hand) |
| A3 | Claude Code is the right first client | Med-high | swap to Copilot + GitHub allow-list |
| A4 | MVP = generate-and-export (no live hook) | High | client hook becomes MVP-critical (bigger) |
| A5 | Managed `allowedMcpServers` is the right export target | Medium | fall back to project `.mcp.json` + docs |
| A6 | Existing scorer + enriched text ranks "relevantly" | Medium | add publisher/verification/stars signal |
| A7 | Sandbox summary beats formal receipt | Medium | keep receipts high-risk only |
| A8 | CHECK migration safe via rebuild | High | store sanction in JSON blob (no CHECK change) |
| A9 | `adoption_decisions` extendable to pack+client | High | use extended `pack_overrides` instead |
| A10 | Curation+repo-fit+export is a defensible seam | Medium | pivot to interop (emit into their catalogs) |

## 13. Risks & mitigations

- **Incumbents absorb the layer (Docker/ToolHive/Socket).** Own the narrow curation+repo-fit+export seam; exporters *feed* their planes; move fast on one client.
- **"Another approval queue" → shadow usage.** Lead with a fast path; everything non-blocking; export must beat hand-curation on time (baseline in P3-2).
- **Differentiator's behavioral evidence doesn't exist (verified).** MVP ships static map + export (still differentiated); probe is costed, gated, high-risk-only.
- **Exporter governs the wrong surface (user-scoped blind spot).** Target managed allow/deny; be explicit it's admin-applied.
- **CHECK-migration corrupts local DB.** Back up in-migration; rebuild pattern; idempotency + preservation tests.
- **Ranker adapter regresses scan path / leaks privates.** Public wrapper; `personalize_verdicts` untouched; back-compat; regression test.
- **Launch — `.tcss`/burned tags.** Verify the built wheel; tag-push dance; never reuse a version.
