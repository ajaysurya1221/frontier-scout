# Internal Rigor Gate 2 — Report

**Date:** 2026-06-05 · **Branch:** `pivot/sanctioned-packs` · **Scope:** the sanctioned-MCP-packs
artifact as a *research-driven product artifact + local preview candidate*.

> This gate establishes **packaging, claim honesty, and technical coherence. It is not market
> validation.** No demand, design-partner completion, PMF, or adoption is claimed. The human-session
> gate in [`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md) remains **0/5**.

---

## 1. Verdict: **PASS WITH RESIDUALS**

The packs artifact is safe to treat as a local preview / research artifact: full suite green, wheel
builds and bundles its assets, the installed wheel runs the offline loop cleanly, and no user-visible
packs output implies execution, cross-client support, runtime enforcement, or validation. Residuals are
**out-of-scope-by-design** (the radar/lab product's Tech-Radar vocabulary) or **intentional** (the
`formal_receipt` variant key, kept per the hardening spec) — none compromise the packs surface (§7, §8).
Three post-draft skeptic reviews ran: packaging **✅ complete**; claim-honesty and rigor each surfaced
**one minor fix, both applied** (a "partner's choice" CLI leak and a README enforcement implication) —
see *Reviews* below.

## 2. Commit tested
Baseline: **`b8cafdb`** (`pivot: harden claim honesty before internal validation`). This gate adds a
display-only verdict relabel (Task 2) + a portable test fix (Task 5), committed as the **Gate-2 commit**
on `pivot/sanctioned-packs` (hash in the session summary). Not pushed, not tagged, not released.

## 3. Test command results
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/miniconda3/bin/python -m pytest -m "not live" -q`
→ **663 passed, 0 failed** (was 659/3 at the start of this gate; the +1 is the new relabel test).
`ruff check` + `ruff format --check` clean on all changed source. (`tests/test_implement.py` carries
pre-existing format drift on lines this gate did not touch; it is outside the repo's lint scope and was
deliberately not reformatted to keep the diff surgical.)

## 4. Environment-only failures
**None remaining.** The 3 previously-known env-only failures —
`test_implement.py::{test_live_run_applies_and_tests, test_live_run_reports_failure,
test_keep_with_failed_status_still_discards}` — shelled out to bare `python` (absent on PATH locally).
Fixed in **Task 5** by switching the three test *fixtures* to `f"{sys.executable} -m pytest …"` (test-data
only; no product change). They now pass locally **and** stay portable on CI.

## 5. Built-wheel smoke
- Clean build: `rm -rf dist build *.egg-info && python -m build` → `dist/frontier_scout-1.8.1-py3-none-any.whl`
  (370 KB) + sdist. (Local preview build of the working tree; **no version bump / no release**, per constraints.)
- **Package data present (the load-bearing gotcha):** the wheel bundles `frontier_scout/tui2/theme.tcss`,
  `frontier_scout/tui3/theme.tcss`, `frontier_scout/tui3/widgets.py`, and the full `tui3/` package.
  Entry point `frontier-scout = frontier_scout.cli:main`.
- Clean venv install + CLI help (all from the installed wheel): `--help`, `packs --help`,
  `packs candidates --help`, `packs export --help` all work; `--client` help reads *"Claude Code only
  today; copilot/cursor are roadmap (selecting them errors)."*

## 6. Installed-wheel e2e demo (offline / keyless, temp HOME + temp repo)
| Step | Result |
|---|---|
| `packs candidates` | 6 servers, `[needs review — static only]`, footer "Static analysis only; no MCP server was executed." |
| `packs candidates --json` | parses; 6 rows; keys incl. `verdict`, `verdict_label`, `requires_review` |
| `packs proof` | "verdict review", "no server was started or executed", "REVIEW - … behavioral evidence recommended", "generated-by … no server executed" — **no "trial"** |
| `packs sanction time` (low-risk) | "Sanctioned … (static verdict: assess) …" |
| `packs export` | writes `managed-settings.json` + `.mcp.json`; prints "static export, not runtime enforcement" |
| managed/project shapes | `allowManagedMcpServersOnly`/`allowedMcpServers`(single-key serverCommand)/`deniedMcpServers`; project `mcpServers` → `type/command/args/env` — **match fixtures** |
| `packs export --client copilot` | **rc=2**, "Copilot/Cursor export is roadmap", **no output dir created** |
| repo mutation | **REPO UNCHANGED** (md5 of recursive listing identical before/after) |
| secrets | none printed (demo data carries none; `sanitize_sensitive_text` applied) |
| network | none required (keyless demo path; `--discover` not used) |
| `stats` funnel | records candidates_viewed/safety_viewed/sanctioned/exported locally |

## 7. Claim-boundary grep (source + installed package)
Installed **packs surface** (`safety_summary.py`, `proof_variants.py`, `pack_flow.py`, `cli.py`): no
user-facing `trial`/`sandbox`/`receipt`/`signed-by`. Every hit is logic (`verdict in ("adopt","trial")`),
an internal key (`formal_receipt`), the back-compat alias, the relabel helper, or a **deferred** docstring
("behavioral sandbox evidence is a separate, gated V1 build"). `signed-by`: **0**. Source-wide counts and
classification:

| Term | Count | Classification |
|---|---|---|
| `trial` | 245 | The ThoughtWorks Tech-Radar verdict ring (`adopt/trial/assess/hold`) across the radar/report/TUI/deps. Packs human output relabels to `review` (Task 2). Out of packs scope. |
| `receipt` | 86 | `trials.py` lab/deps "trial receipt" (a *different* feature that genuinely runs a hermetic trial) + the kept `formal_receipt` variant key (static content). |
| `sandbox` | 26 | Lab/scout/policy (lab genuinely sandboxes) + the packs **deferred-V1** docstring. None claim packs sandboxes. |
| `block` | 74 | Code keywords + the sanction risk-gate ("blocked" = won't sanction without acknowledgement, not install-blocking). |
| `registry` | 49 | FS *reads from* the MCP/package registries; never claims to **be** one. |
| `cursor` | 33 | Mostly TUI table cursor + repo `.cursor` detection; client uses are FIX-1 gated. |
| `copilot` | 14 | FIX-1 gated choices/help + the GitHub MCP **server** URL (`api.githubcopilot.com`, data). |
| `docker` | 11 | Repo Docker detection + external registry type — not a Docker exporter claim. |
| `enforce` | 6 | DB FK/gateway-budget enforcement + the FIX-6 "**not** runtime enforcement" denial. |
| `secure` | 1 | `securerandom` module name. |
| `signed-by` / `governance` / `cross-client` | 0 | Removed / never in source `.py`. |

## 8. Tech-Radar `trial`/`review` residual — **FIXED (display-only)**
Resolved in Task 2: the raw tier stays in `summary["verdict"]` (data contract: `adopt/trial/assess/hold`,
asserted by tests, used by the radar) and a new display-only `verdict_label` maps `trial`→`review`,
applied across every packs human surface (static safety summary incl. the policy-summary prefix, the
three proof variants, the sanction line) and surfaced transparently in `--json` (both `verdict` and
`verdict_label`). No verdict logic changed; the radar/dossier/deps verdict display is untouched.

## Reviews (Task 8) & post-review fixes
Three skeptic subagents ran against the built wheel + installed venv + this report:
- **Packaging Skeptic → ✅ wheel complete & self-sufficient.** 111/111 modules match source; both `tui2`
  + `tui3` `theme.tcss` present + declared in `pyproject.toml` + `MANIFEST.in`; a **headless Textual boot
  resolved the stylesheet** (the StylesheetError crash path is proven absent, not inferred); genuine
  non-editable install; honest strings present (not a stale build). Non-blocking note: `scripts/` +
  `outputs/` ship as top-level packages (required by the live scan's
  `Path(__file__).parent.parent / "scripts"` import) — a future `_vendor/` cleanup, out of gate scope.
- **Claim-Honesty Skeptic → 1 Minor, FIXED.** `packs proof` printed "Record the **partner's** choice…",
  leaking the internal design-partner framing into shipped output. Fixed → "Record **your kept
  variant**…" (+ the `--keep` help text); verified absent from the rebuilt wheel (`partner` count = 0).
  All other surfaces verified honest (static-only disclaimers, hard-gated clients, non-blocking guard,
  reads-not-owns the registry).
- **Solo-Founder Rigor Skeptic → "intellectually honest to continue as a preview artifact."** The work
  separates coherence (agent-verifiable) from demand (not), quarantines synthetic feedback, and declines
  to build the sandbox the synthetic panel "asked" for. **1 real drift, FIXED:** README still shipped
  "the surface that governs even user-scoped installs" (an enforcement implication the product
  disclaims). Fixed → dropped; the bullet now ends "it doesn't deploy or enforce anything itself." Its
  warning is recorded in §12.

Post-review: wheel **rebuilt** from the fixed source and re-verified (proof output clean; honest strings
intact). Two surgical string fixes; full suite still **663 passed / 0 failed**.

## 9. — 11. Required statements
9. **This gate establishes packaging, claim honesty, and technical coherence. It is not market validation.**
10. **Frontier Scout remains Claude Code managed-config export first today. Copilot/Cursor/Docker are roadmap unless separately implemented.**
11. **Current sanctioned-pack safety output is static analysis only; no MCP server is behaviorally executed.**

## 12. Recommended next step
The artifact is a sound local preview. The remaining work is **not more code, and not another gate**:
the only thing that can move the verdict from "coherent" to "wanted" is **5 real external design-partner
sessions** ([`HUMAN_VALIDATION_SCRIPT.md`](HUMAN_VALIDATION_SCRIPT.md) →
[`VALIDATION_LEDGER.md`](VALIDATION_LEDGER.md)).

**Heed the rigor skeptic's warning:** this gate is the *last* honest non-human task. A Gate 3, a second
synthetic panel, or another wheel-smoke would be **avoidance** — the marginal coherence gain is ~zero and
the only unmet variable is demand. So: do **not** build V1 features (behavioral sandbox, cross-client
export, CI guard) and do **not** run another internal rigor pass before a GO from real humans. The single
most rigorous next action is **session 1 of 5**. (If a release is ever pursued later, the only mechanical
follow-up is a version bump + the already-green `release.yml` stylesheet guard — release work, out of
scope here.)
