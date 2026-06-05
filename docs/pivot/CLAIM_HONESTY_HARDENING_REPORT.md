# Claim-Honesty Hardening Report

**Sprint:** `pivot: claim-honesty hardening before internal validation` · **Date:** 2026-06-05 ·
**Branch:** `pivot/sanctioned-packs`

> This sprint makes the **sanctioned-MCP-packs** surface tell the truth about what it does (static,
> Claude-Code-first, no execution, no enforcement). It is **copy/label/test-level**, TDD-driven, and
> changes no product behavior except refusing to emit Claude config under a Copilot/Cursor label.

---

## 1. Changed files

**Source (6):**
- `frontier_scout/cli.py` — FIX 1 client gate + help text; FIX 2 flag/field/disclaimer; FIX 3 `--keep` choices; FIX 5 verdict label; FIX 6 export disclaimer; (post-review) `(static verdict: …)`.
- `frontier_scout/proof_variants.py` — FIX 3 `sandbox_summary`→`static_safety_summary` (+ legacy alias); FIX 4 attestation wording; docstring.
- `frontier_scout/safety_summary.py` — FIX 2 `requires_trial`→`requires_review` (+ comment honesty).
- `frontier_scout/pack_flow.py` — FIX 1 false "all clients share shapes" comment corrected; removed dead, misleadingly-named `SUPPORTED_CLIENTS` constant.
- `frontier_scout/policy.py` — (post-review, Subagent 1 Critical) "sandbox evidence **required**" → "behavioral evidence **recommended** before adoption" (3 messages; shared engine, prose only).
- `README.md` — (post-review, Subagent 3) hero line tightened: "managed-config export … a fragment an admin deploys … emits it; your platform deploys it."

**Tests (6):** `tests/test_claim_honesty.py` (new, 8 tests); updated `test_proof_variants.py`, `test_packs_proof_cli.py`, `test_packs_candidates_cli.py`, `test_safety_summary.py`, `test_sanction_gating.py`.

**Docs (4 operational + this report):** `docs/validation-session-kit.md`, `validation-protocol.md`, `validation-dry-run.md`, `docs/pivot/HUMAN_VALIDATION_SCRIPT.md` (propagate FIX 3 rename + reflect that the fixes landed). Historical analysis docs (`SYNTHETIC_VALIDATION_REPORT.md`, `REVISED_IMPLEMENTATION_PLAN.md`, `OVERNIGHT_IMPLEMENTATION_REPORT.md`) were **not** edited (see §4).

---

## 2. The six fixes — exactly how each was handled

**FIX 1 — Client-scope honesty.** The CLI keeps `--client {claude-code,copilot,cursor}` so it can emit a
*clear* message (not a generic argparse error), but the packs dispatch now hard-gates: any client other
than `claude-code` prints to **stderr** `"Not implemented: Frontier Scout currently exports Claude Code
managed-config fragments only. Copilot/Cursor export is roadmap."` and returns **exit code 2** — before
any handler runs, so **no Claude config is ever emitted under a Copilot/Cursor label**. All five
`--client` help strings now read *"Claude Code only today; copilot/cursor are roadmap (selecting them
errors)."* The false comment in `pack_flow.export_config` ("all MVP clients consume the same shapes") was
corrected, and the unused, misleadingly-named `SUPPORTED_CLIENTS` constant was deleted.

**FIX 2 — No "trial" wording for static analysis.** The candidate flag `[trial required]` →
`[needs review — static only]`; the summary field `requires_trial` → `requires_review` (source + JSON +
3 tests); the candidates text output now ends with **"Static analysis only; no MCP server was
executed."** The global Tech-Radar `Verdict` enum (`adopt/trial/assess/hold`) was **left intact** — see
§4; it is a recommendation ring, not an execution claim, and is rendered beneath the no-execution
disclaimer.

**FIX 3 — `sandbox_summary` → `static_safety_summary`.** Renamed in `VARIANTS`, the rendered dict key,
the `--keep` CLI choices, the docstring, the validation kit, and tests. A **back-compatible internal
alias** (`_LEGACY_VARIANT_ALIASES`) normalizes any persisted/legacy `sandbox_summary` to
`static_safety_summary` in `record_preference`, so the misleading name is **never shown or recorded**. No
sandbox was built.

**FIX 4 — Attestation honesty.** In the formal proof variant: `ADOPTION RECEIPT (static)` →
`STATIC ADOPTION ASSESSMENT`; `signed-by: frontier-scout …` → `generated-by: frontier-scout (static
analysis; no server executed)`. The `formal_receipt` **variant is kept** (per the fix spec) but now
renders as an explicitly generated, static artifact — no implied signature or witnessed runtime event.

**FIX 5 — Define the `(assess)` parenthetical.** The sanction success line changed from
`Sanctioned <s> (assess) for <client>.` to `Sanctioned <s> (verdict: assess) for <client>.` — the bare,
undefined shorthand is now a labelled verdict.

**FIX 6 — Export value-prop / honesty line.** `packs export` now prints **"Generated Claude Code
managed-config fragment for admin review; this is a static export, not runtime enforcement."** It names
managed config for Claude Code only and does not claim the file auto-governs user-scoped installs. The
line is text-only; the generated `managed-settings.json` / `.mcp.json` remain valid JSON (asserted by
test).

---

## 3. Tests added / updated

- **New `tests/test_claim_honesty.py` (8):** Claude-Code client works; copilot/cursor hard-gated with no
  config emitted; candidates drop "trial" wording + state static; summary uses `requires_review`;
  sanction labels the verdict; export prints the disclaimer + writes valid JSON.
- **Updated:** `test_proof_variants.py` (static_safety_summary key; formal variant is STATIC/generated,
  not signed; **new** legacy-alias normalization test); `test_packs_proof_cli.py` (variant set, `--keep`,
  recorded value); `test_packs_candidates_cli.py`, `test_safety_summary.py`, `test_sanction_gating.py`
  (`requires_review`).
- **TDD discipline:** all assertions were written first and confirmed **red for the right reasons** (15
  failures: `KeyError: requires_review`, missing gate, old variant key, missing disclaimers, old receipt
  wording) before any source change, then driven **green**.

**Verification:** `659 passed, 3 failed` on the full non-live suite. The 3 failures are the **known
environment-only** `tests/test_implement.py` cases (they shell out to bare `python`, absent on PATH
locally; they pass on CI) — `assert 'error' == 'failed'`. **Not introduced by this sprint** (baseline
651 + 8 new = 659 passing). `ruff check` clean; `ruff format --check` clean on changed files. CLI smoke
(`--help`, `packs --help/candidates --help/export --help`, and a full candidates→sanction→export→proof
run) confirms the honest strings in real output.

---

## 4. Remaining risky terms — and why they are acceptable

| Term / location | Verdict | Why |
|---|---|---|
| **`trial` / `assess` Verdict enum** (`policy.py`, TUI, report — global) | Keep | The ThoughtWorks Tech-Radar rings (adopt/trial/assess/hold), load-bearing across ~15 files of the radar/report/TUI. Renaming is non-surgical and breaks legitimate semantics. In the packs flow they render **beneath** `_Static analysis only — no server was started or executed._`, so they read as a recommendation ring, not execution. |
| **`policy.py` "sandbox evidence required"** (`policy.py:133/169/176`) | **FIXED post-review** | Subagent 1 rated this **Critical** — it contradicted the no-execution disclaimer (present-tense gate implying FS sandboxes). Reworded to "behavioral evidence **recommended** before adoption" — honest for both the lab (which can provide it) and packs (which recommends it); no verdict/rule_id/logic change; no test asserted the old strings. |
| **`verdict: trial` token** in proof/approval output | Keep (accepted) | The ThoughtWorks Tech-Radar ring (worth trialing), not a claim FS ran a trial — renders under the no-execution disclaimer and the now-honest policy text. A display-only `trial`→`review` relabel is a §7 next-gate candidate; remapping now would desync the shown word from the JSON verdict value + global enum. |
| **`formal_receipt` variant key** | Keep | Kept per FIX 4 ("keep the formal receipt proof variant"); its content is now explicitly `STATIC ADOPTION ASSESSMENT` / `generated-by`. "receipt" survives only as the A/B/C label. |
| **`trials.py` "trial receipt", lab `--sandbox` flag** | Keep | A **different feature** (the dependency/lab hermetic trial) that genuinely installs + imports — "trial"/"sandbox" are technically true there. Out of the MCP-packs claim surface. |
| **"MCP-registry", pypi/npm/docker/oci** (`packs.py`, `cli.py`) | Keep | FS *reads from* these external registries; it never claims to **be** a registry. True. |
| **`api.githubcopilot.com/mcp/`** (`packs.py` demo data) | Keep | The real GitHub MCP **server** endpoint (data for the `github` demo server), not a Copilot-**client** export claim. |
| **`.cursor` / `docker` detection** (`profile.py`, `scout.py`) | Keep | Repo-profiling signals (does the repo use Cursor/Docker), not packs export claims. |
| **"cross-client" in `REVISED_IMPLEMENTATION_PLAN.md` / `OVERNIGHT_IMPLEMENTATION_REPORT.md`** | Left (historical) | Dated planning/report artifacts; not edited per the "don't rewrite historical reports" rule. The **authoritative current-state** docs (README, quickstart, this report) state Claude-only-today. |
| **Risky terms in `HUMAN_VALIDATION_SCRIPT.md` / `SYNTHETIC_VALIDATION_REPORT.md` "must-not-claim" lists** | Keep | Intentional — they instruct the facilitator **not** to make those claims. |

---

## 5. Three independent reviews (run after implementation, against real code + live CLI)

- **Subagent 1 — Claim Honesty Auditor:** **1 Critical** — the shared policy engine printed "sandbox
  evidence **is required** before adoption" inside the packs static summary, under "no server was
  executed" → self-contradiction. **Fixed** (below). **1 Minor** — unlabelled `(verdict: assess)` →
  fixed. No Category 2–6 residuals; README/quickstart make no registry-ownership / PMF /
  design-partner-complete / install-blocking claims.
- **Subagent 2 — Spec Compatibility Auditor:** **✅ accurate throughout.** `managed-settings.json`
  (allowManagedMcpServersOnly + single-key allow/deny entries) and `.mcp.json` (`mcpServers` map) match
  the fixtures + spike doc; the exporter docstring, FIX 6 line, and quickstart "Honest scope" note frame
  governance as Claude's admin-deployed surface (emit-vs-deploy split), never FS auto-governance.
- **Subagent 3 — Competitor Red Team (positioning only):** flagged the README "control-plane export /
  governs even user-scoped installs" hero line as leaning on Anthropic's enforcement (constraint #4).
  **Tightened** (below). Confirmed the defensible seam: repo-aware prioritization + a coexisting
  generated Claude fragment — *as long as* "static / pre-deployment / admin-deployed" qualifiers stay on.

### Post-review fixes applied (TDD-checked; full suite still 659 pass / 3 env-only)
- **Critical (policy honesty):** `policy.py` messages "sandbox evidence **is required**" →
  "behavioral evidence **is recommended** before adoption" — the packs summary no longer contradicts its
  own no-execution disclaimer (verified live); no verdict/logic change; no test asserted the old strings.
- **Minor:** sanction success line → `Sanctioned <s> (static verdict: assess) for claude-code.`
- **Positioning (constraint #4):** README hero → "One-step **managed-config** export … a fragment **an
  admin deploys** … Frontier Scout emits it; your platform deploys it" (drops the "control-plane" label
  + the "drops straight into" auto-deploy implication).

---

## 6. Required statements

1. **This sprint improves claim honesty and technical coherence. It is not market validation.**
2. **Frontier Scout is Claude Code managed-config export first today. Copilot/Cursor/Docker are roadmap
   unless separately implemented.**
3. **Current safety output is static analysis only; no MCP server is behaviorally executed.**

---

## 7. Next recommended internal rigor gate

Claim honesty is now enforced at the packs surface (the policy self-contradiction is fixed). The next
internal gates, in order: (1) a **display-only verdict relabel** — decide whether the packs renderers
should show the Tech-Radar `trial` ring as `review`, so a static-only product never surfaces the word
"trial" (display-only; leave the global `Verdict` enum + JSON value intact); (2) a **built-wheel smoke**
(`python -m build` + run the bundled CLI) to confirm the honest strings ship in the artifact, not just
the source tree; (3) only then spend the scarce resource — **5 real external design-partner sessions** —
which remain the only thing that can prove demand.
