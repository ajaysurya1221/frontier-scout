# Overnight Implementation Report — Frontier Scout pivot

Branch: `pivot/sanctioned-packs` (8 commits off `4154c8b`). No push / deploy / publish / prod
migration performed. Plan: `docs/pivot/REVISED_IMPLEMENTATION_PLAN.md`.

## 1. Executive summary

Implemented the **revised pivot** end-to-end across all five phases: Frontier Scout now turns
"can we use this MCP server?" into a **repo-ranked, sanctioned MCP-server pack** for a coding
assistant (Claude Code first), with a **static safety map** (capability + policy, no execution),
**risk-gated sanctioning**, and a **one-step export into Claude managed config**
(`allowedMcpServers`/`deniedMcpServers` + `.mcp.json`). The whole journey runs **keyless and
offline** by default. Everything was built test-first (TDD). The full non-live suite is **642
passed, 3 failed** — the 3 are the pre-existing, documented env-only `test_implement.py` cases
(identical to the pre-change baseline). A real CLI end-to-end smoke passes by hand.

## 2. What changed from the previous plan

The follow-up research (`research_2.pdf`) moved the wedge **upstream** (install/approval time) and
killed the GitHub-Action/CI-receipt framing. The verified-against-code correction: the repo's
sandbox **cannot trial an MCP server** (only installs a package), so **behavioral sandbox evidence
was demoted to a gated V1 build** and the MVP proof is a **static** safety map. The exporter target
was corrected to the **managed allow/deny** surface (governs user-scoped `~/.claude.json`). Backstage
was dropped in favor of Claude/GitHub/Docker control planes. See §1–4 of the revised plan.

## 3. What was implemented

- **Phase 0:** branch, recorded baseline, `DEPRECATIONS.md`, repositioned README/CLI copy, two
  feasibility spikes (`docs/spike-mcp-probe.md`, `docs/spike-claude-config.md` + golden fixtures).
- **Phase 1:** `"sanctioned"` pack state + idempotent CHECK-widening migration (v7); enriched
  `PackCandidate` (category/description/tags/server_meta/repo_fit) + offline MCP-registry parser;
  repo-aware ranker adapter (`evaluate.repo_fit`, `rank_candidates_for_repo`); `pack_overrides`
  reader + precedence enforcement; pack/client-scoped `adoption_decisions` (v8); static
  safety-summary renderer.
- **Phase 2 (MVP):** `exporters/claude_config.py` (managed + project faces, golden-matched,
  redacted); `pack_flow.py` orchestration; CLI `packs candidates --repo --client`, risk-gated
  `packs sanction/unsanction`, `packs export`; offline demo pack; persisted enriched fields (v9);
  e2e flow.
- **Phase 3:** local opt-in telemetry (`pack-events.jsonl`, off by default, redacted, zero-egress)
  + `frontier-scout stats`; A/B/C proof-variant harness; `docs/validation-protocol.md`.
- **Phase 4:** Incident Change Scout parked behind `FRONTIER_SCOUT_EXPERIMENTAL`; non-blocking
  `guard --notify`; quickstart; README killer-workflow repositioned.

## 4. What was not implemented and why

- **Behavioral MCP sandbox probe** (start a server, list tools): net-new (needs an `mcp` SDK dep +
  transport client). Demoted to V1, **gated on Phase-3 validation** (Spike A costed it).
- **Second client (Copilot) + GitHub allow-list / Docker catalog exporters:** V1, gated on demand.
- **Interactive TUI pack flow:** V1; the CLI is the validation artifact (TUI not needed for the
  2-week test, and it's the riskiest surface re: golden-frame tests).
- **GitHub Action / Backstage:** deliberately out of scope per the research (red lines).
- **Running the actual 5 design-partner sessions:** can't happen autonomously; the protocol +
  instrumentation to run them are built.

## 5. Which phases were completed

**All five (0–4)** of the *buildable* scope completed and committed.

## 6. Which phases were partial or skipped

None skipped. Phase 4 is "complete for buildable work" — its V1 items are intentionally gated on
Phase-3 validation data (documented, not skipped).

## 7. Files changed by area

- **New modules:** `frontier_scout/{pack_flow,telemetry,proof_variants,safety_summary}.py`,
  `frontier_scout/exporters/{__init__,claude_config}.py`.
- **Edited:** `frontier_scout/{cli,packs,store,evaluate}.py`, `README.md`, `CHANGELOG.md`.
- **Parked (gated, not deleted):** `frontier_scout/platform/incident_change_scout/*` (via `cli.py`).
- **Docs:** `docs/pivot/{REVISED_IMPLEMENTATION_PLAN,OVERNIGHT_IMPLEMENTATION_REPORT}.md`,
  `docs/{spike-mcp-probe,spike-claude-config,validation-protocol,sanctioned-packs-quickstart}.md`,
  `DEPRECATIONS.md`.
- **Tests/fixtures:** 14 new `tests/test_*.py`, `tests/fixtures/claude_config_{managed,project}.json`.

## 8. Frontend changes

This is a CLI/TUI app (no web frontend). CLI surface added under `packs`:
`candidates --repo --client [--discover] [--json]`, `sanction <server> [--acknowledge-risk]
[--approver] [--reason]`, `unsanction <server>`, `export --client --target`; plus top-level
`stats` and `guard --notify`. Text + `--json` output; loading is synchronous/offline; **empty
states** ("no sanctioned servers" → empty `mcpServers`) and **error states** (unknown server →
exit 1 message; high-risk blocked → safety summary + guidance, exit 1) are handled. The Mission
Control TUI was left intact (demoted in copy, not code).

## 9. Backend/API changes

No web API. New library "API": `pack_flow.{get_candidates,sanction_server,unsanction_server,
export_config}`, `safety_summary.{build_safety_summary,render_safety_summary,is_high_risk}`,
`exporters.{to_managed_config,to_project_mcp_json,export_claude_config}`,
`telemetry.{record_event,read_events,summarize}`, `proof_variants.{proof_variants,record_preference}`,
`packs.{rank_candidates_for_repo,pack_candidate_to_fit_input,apply_pack_overrides,demo_mcp_servers,
_parse_registry_payload}`, `evaluate.repo_fit`, `store.{save_adoption_decision,list_adoption_decisions,
list_pack_overrides}`. All deterministic/offline; the only network path is opt-in `--discover`.

## 10. Data model or persistence changes (SQLite, additive + idempotent)

- **v7:** widen `pack_candidates.state` CHECK to allow `'sanctioned'` (in-place table rebuild,
  explicit columns, rows preserved).
- **v8:** `adoption_decisions` gains `pack_slug` + `client` (nullable ALTER; dormant-table-safe)
  + first writers/readers.
- **v9:** `pack_candidates` gains `payload_json` (nullable ALTER) to persist
  category/description/tags/server_meta/repo_fit.
- New local files under `$FRONTIER_SCOUT_HOME`: `pack-events.jsonl` (opt-in telemetry).
- All migrations run inside `init_db`, are idempotent, and preserve existing rows (tested).

## 11. Copy/positioning changes

CLI description, README hero/About/killer-workflow, and `CHANGELOG` repositioned from "AI-adoption
radar" → **"sanctioned MCP-server packs for coding assistants."** Radar/BYO-LLM demoted to "the
ranking engine behind the product" (kept, not removed). `DEPRECATIONS.md` records the parked/softened
surfaces. Demo-diff guard stayed green throughout (no `demo/` drift).

## 12. Tests added or updated

14 new test files (~42 new passing tests): `test_claude_config_fixtures`, `test_store_migration`,
`test_packs_registry`, `test_packs_ranking`, `test_overrides_enforcement`, `test_safety_summary`,
`test_exporters_claude`, `test_pack_persistence`, `test_sanction_gating`, `test_packs_candidates_cli`,
`test_pack_flow_e2e`, `test_pack_telemetry`, `test_proof_variants`, `test_phase4_hardening`.

## 13. TDD evidence (test written first → observed RED reason → GREEN)

Every behavior change followed red→green. Observed failing-first reasons, by task:

| Task | Test (first) | RED reason observed | Then |
|---|---|---|---|
| P1-1 | test_store_migration | `ValidationError` (Literal) + `IntegrityError: CHECK constraint failed` + v7 not stamped | GREEN |
| P1-2 | test_packs_registry | `AttributeError: 'PackCandidate' object has no attribute 'category'` | GREEN |
| P1-3 | test_packs_ranking | `ImportError: cannot import name 'pack_candidate_to_fit_input'` | GREEN |
| P1-4 | test_overrides_enforcement | `ImportError: cannot import name 'apply_pack_overrides'` | GREEN |
| P1-5 | test_safety_summary | `ModuleNotFoundError: frontier_scout.safety_summary` | GREEN |
| P2-1 | test_exporters_claude | `ModuleNotFoundError: frontier_scout.exporters` | GREEN |
| P2-3 | test_sanction_gating | `ImportError: cannot import name 'pack_flow'` | GREEN (+ caught a real bug: server_meta config keys polluting capability classification) |
| P2-2/4 | test_packs_candidates_cli / test_pack_flow_e2e | `error: unrecognized arguments: packs candidates --repo` | GREEN |
| P3-1 | test_pack_telemetry | `ImportError: cannot import name 'telemetry'` | GREEN |
| P3-2 | test_proof_variants | `ModuleNotFoundError: frontier_scout.proof_variants` | GREEN |
| P4-1 | test_phase4_hardening | `--notify` unrecognized + incident not gated | GREEN |
| P0-4 | test_claude_config_fixtures | (data) shape-validation test | PASS |

Copy/docs/fixtures (P0-1/2/3, validation-protocol, quickstart) used smoke/build/shape verification
(TDD not meaningful) — stated per-card in the plan.

## 14. Commands run and results

- `ruff check frontier_scout/ outputs/ tests/...` → **All checks passed**.
- `ruff format --check` (new modules) → **already formatted**.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -m "not live" -q` → **642 passed, 3 failed**
  (3 = env-only `test_implement.py`; baseline was 600 passed, 3 failed).
- `python -m build` → **success**; wheel bundles `frontier_scout/tui2/theme.tcss` +
  `frontier_scout/tui3/theme.tcss`.
- `detect-secrets` (CI-style, no baseline) → **0 findings in committed files** (one fake test key
  allowlisted via `# pragma: allowlist secret`).
- `frontier-scout demo --no-serve && git diff --exit-code -- demo/` → **clean** throughout.
- Real CLI e2e smoke (candidates → sanction[blocked/ack] → export → stats) → **works**; emitted a
  valid `managed-settings.json`.

## 15. Known failures or limitations

- **3 env-only test failures** (`tests/test_implement.py::test_live_run_*`,
  `test_keep_with_failed_status_still_discards`): they shell out to bare `python` (not on this
  conda PATH) and assert `'failed' == 'error'`. **Pre-existing**, documented in CLAUDE.md, identical
  to the pre-change baseline — **not caused by this work**. Pass on CI.
- **`make type` (mypy)** is not runnable locally (mypy not installed in this conda env). CI runs it
  on `platform/` only, which this pivot does not touch.
- `design_handoff_mission_control_v6/*` trips detect-secrets locally, but those files are
  **untracked** (never reach CI). Not introduced here.
- The MVP safety read is **static** (no behavioral execution). Live MCP-registry `--discover`
  makes a network call (opt-in only).

## 16. Assumptions made

(See revised plan §12 for the full table.) Key ones: static safety map is enough to start (A2);
Claude Code is the right first client (A3); generate-and-export — not a live client hook — is
enough for the MVP (A4); managed `allowedMcpServers` is the right export target (A5); the demo pack
of real popular MCP servers is an acceptable keyless default (new — made to avoid the global
`--demo` alias collision and to ship keyless). All flagged for design-partner validation.

## 17. Risks

- Incumbents (Docker/ToolHive/Socket) absorbing the curation+export layer; "another approval queue"
  → shadow usage; the static-vs-behavioral proof question; exporter governance-reach (managed config
  is admin-deployed). Mitigations in the revised plan §11 and the validation protocol (kill criteria).
- Technical: the v7/v8/v9 migrations mutate a user's local `db.sqlite` — idempotent + row-preserving
  + tested, but worth a backup note in release docs.

## 18. Manual QA steps

```bash
export FRONTIER_SCOUT_HOME=$(mktemp -d) ; R=$(mktemp -d) ; echo '{"mcpServers":{}}' > "$R/.mcp.json"
python -m frontier_scout packs candidates --repo "$R" --client claude-code      # 6 ranked servers
python -m frontier_scout packs sanction io.modelcontextprotocol/time --repo "$R"  # low-risk: ok
python -m frontier_scout packs sanction com.github/github --repo "$R" ; echo $?    # high-risk: blocked, exit 1
python -m frontier_scout packs sanction com.github/github --repo "$R" --acknowledge-risk
python -m frontier_scout packs export --client claude-code --target "$R/out"      # writes managed + project
cat "$R/out/managed-settings.json"                                                # allow/deny fragment
FRONTIER_SCOUT_TELEMETRY=1 python -m frontier_scout stats                          # funnel
python -m frontier_scout guard --repo "$R" --notify ; echo $?                      # non-blocking: exit 0
python -m frontier_scout incident demo ; echo $?                                  # parked: exit 2 unless FRONTIER_SCOUT_EXPERIMENTAL=1
```

## 19. Recommended next action when I return

**Review the branch, then run the 2-week validation protocol** (`docs/validation-protocol.md`) with
5 platform/AppSec leads — do **not** build the behavioral probe / Copilot / Docker exporters first.
The MVP is the validation artifact. If the gate passes (≥3/5 prefer the pack; ≥1 export snap-in),
build the V1 items in order: behavioral MCP probe (high-risk only), Copilot + GitHub allow-list
exporter, non-blocking notifier in CI. If it fails the kill criteria, re-scope per the protocol.
Open the PR below when ready.

## 20. Suggested PR title

`pivot: sanctioned MCP-server packs for coding assistants (Claude Code) — repo-ranked, risk-gated, managed-config export`

## 21. Suggested PR description

> Repositions Frontier Scout from a broad "AI-adoption radar" to a focused **sanctioned
> MCP-server packs** product, per follow-up market research (`traction_research/research_2.pdf`).
>
> **What:** `frontier-scout packs candidates/sanction/export` — build a repo-ranked, sanctioned set
> of MCP servers for Claude Code, with a static capability+policy safety map, risk-gated approval,
> and a one-step export into managed config (`allowedMcpServers`/`deniedMcpServers` + `.mcp.json`).
> Keyless and offline by default. Plus opt-in local telemetry + `stats`, an A/B/C proof-variant
> harness, and a non-blocking `guard --notify`.
>
> **Why:** the market is consolidating on install-time allowlists/managed configs/catalogs; the
> differentiated layer is repo-aware curation + cross-client export. Behavioral sandbox evidence is
> demoted to a validation-gated V1 (the repo's lab can't trial MCP servers — verified).
>
> **How:** additive SQLite migrations (v7–v9, idempotent, row-preserving); reuses the existing
> deterministic fit scorer, `mcp_audit`, and `policy`. Incident Change Scout parked behind a flag;
> no existing command removed. All local-first / no-telemetry invariants preserved.
>
> **Tests:** 14 new test files (~42 tests), TDD throughout. Full non-live suite **642 passed, 3
> failed** (the 3 are pre-existing env-only `test_implement.py` cases). Build OK; wheel bundles
> `.tcss`; demo-diff clean; detect-secrets clean. Plan: `docs/pivot/REVISED_IMPLEMENTATION_PLAN.md`;
> next step: run `docs/validation-protocol.md`.
>
> 🤖 Generated with [Claude Code](https://claude.com/claude-code)

## 22. Post-implementation code review (addendum)

A senior-reviewer subagent reviewed the full branch (`4154c8b..HEAD`) — running the migrations on a
real legacy DB, blocking the network to prove the offline invariant, and probing redaction/gating.
**No Critical issues.** Three Important findings were fixed (TDD, `tests/test_review_fixes.py`):

- **I-1 (security):** `build_safety_summary` returned raw `description`/`policy_summary`/`findings`,
  so `packs sanction|candidates --json` could emit a secret embedded in a 3rd-party registry
  description. **Fixed** by redacting those fields at the source — so this corrects the earlier
  "redacted" claim: redaction is now applied at construction, not only on the markdown path.
- **I-2:** the project `.mcp.json` exporter collapsed server names to their last path segment, so
  two namespaced servers collided and one was silently dropped. **Fixed** with key de-collision.
- **I-3:** `_candidate_from_row` dropped `freshness_score`/`consensus_score`, so sanctioning a
  stored candidate zeroed them. **Fixed** by carrying the scores (+evidence) through.
- **M-3 / M-4:** `--client` now validated (`choices=`); the remove-override set de-duplicated to one
  constant (`packs.REMOVE_OVERRIDES`).

Accepted-with-note (not fixed): **M-1** (a real secret placed in `server_meta.env` is stored
verbatim in the local DB — normally `""`; the *exported* config is still pattern-redacted) and
**M-2** (project URLs keep their query string; managed URLs are collapsed to `scheme://host/*`).
Both are documented follow-ups; the spike already advises `${VAR}` for env secrets.

Reviewer verdict after fixes: mergeable. (One process note: an over-broad `ruff format frontier_scout/`
briefly reformatted 64 unrelated files; that churn was reverted and only the 5 review-fix files were
reformatted — the final diff is surgical.)
