# Autonomous Implementation Report — Agent Adoption Firewall + Audit Trail MVP

**Date:** 2026-06-06 · **Branch:** `feat/agent-firewall-mvp` (4 commits, not pushed) · **Process:**
Superpowers (brainstorming-via-reality-check → writing-plans → subagent-driven-development → TDD →
verification → security review), executed autonomously with multi-agent workflows (Opus 4.8, 1M context).

---

## 1. Product direction implemented

A **static, advisory, local-first agent adoption firewall + audit trail**, shipped as a new
`frontier-scout agent` command group beside the existing sanctioned-packs engine. It helps a repo owner
answer: *what's risky here before an agent touches code/creds/CI/deploy; what should the agent be allowed to
do; what did a proposed task ask for; was it allow / needs-approval / block; and what receipt can a reviewer
inspect afterward.* It **emits** policy + evidence and **executes nothing** — no agent task, no MCP server,
no network, no secret-value reads. This is a faithful, in-scope instantiation of the wedge endorsed by
[`frontier-scout-strategy-research-2026.md`](frontier-scout-strategy-research-2026.md) (firewall + pack
governance + audit trail, static preflight only); see [`repo-reality-check.md`](repo-reality-check.md) and
the [design spec](../superpowers/specs/2026-06-06-frontier-scout-agent-firewall-mvp-design.md).

## 2. Files changed

**New package** `frontier_scout/agent_firewall/`: `models.py` (pydantic data model), `scan.py` (risk-surface
scanner), `policy.py` (generation + fail-closed loader), `decision.py` (the `check` engine), `receipts.py`
(JSON audit receipts). **New exporter** `frontier_scout/exporters/policy_snippets.py`. **Modified:**
`cli.py` (+174, the `agent` group + dispatch), `doctor.py` (+63, three checks), `exporters/__init__.py`
(re-exports), `outputs/_text.py` (+18, shared `scrub_secrets`), `pyproject.toml` (description + keyword),
`.gitignore` (`.frontier-scout/`). **Docs:** README/ROADMAP/CHANGELOG/DEPRECATIONS, `docs/strategy/*` (reality
check, security review, this report), `docs/superpowers/specs|plans/*`, `docs/examples/agent-firewall/`
(CLI-generated gold path). **~2,014 insertions across 21 code/test files** + docs. 4 coherent commits.

## 3. Commands added

| Command | What it does | Exit codes |
|---|---|---|
| `frontier-scout agent scan [--repo .] [--json] [--strict]` | Enumerate agent-risk surfaces + detected checks | 0 (1 if `--strict` + high surface) |
| `frontier-scout agent policy init [--repo .] [--path] [--force]` | Write conservative `frontier-scout.policy.json` | 0 |
| `frontier-scout agent policy explain [--policy] [--json]` | Human/JSON view of a policy | 0 |
| `frontier-scout agent check "<task>" [--policy] [--changed-files …] [--json]` | Pre-check a proposed task (executes nothing) | 0 allow / 3 needs_approval / 4 block |
| `frontier-scout agent receipts list [--json]` / `receipts show <id> [--json]` | Inspect the audit trail | 0 (1 if not found) |
| `frontier-scout agent export claude\|agents-md\|pr-checklist [--target]` | Emit an advisory snippet | 0 |
| `frontier-scout doctor` | + agent-policy presence/validity + receipts-writable checks | 0 (1 on fail) |

Verbs were chosen to **avoid collisions** with the radar's existing `scan`/`trial`/`policy`/`export` (the
existing `trial`/`deps trial` *execute* a subprocess — reusing the name would have broken the static-only
invariant). The non-executing evaluator is `check`, not `trial`. See [DEPRECATIONS.md](../../DEPRECATIONS.md).

## 4. Tests added

**46 new tests** (full suite 672 → **718, 0 failures**), all in the broad CI pytest step:
`test_agent_models` (4), `test_agent_scan` (4), `test_agent_policy` (6), `test_agent_decision` (6),
`test_agent_receipts` (4), `test_agent_exporters` (4), `test_agent_cli` (5), `test_agent_honesty` (4),
`test_agent_security` (9). TDD throughout (red → green → refactor). Coverage includes the load-bearing
invariants: scan never reads secret contents; `evaluate_task` spawns no subprocess; loader fails closed;
receipts/exports redact secrets; path traversal rejected; honesty copy guards.

## 5. Commands run & results

| Check | Command | Result |
|---|---|---|
| Baseline | `pytest -q` | 672 passed, 0 failed |
| Full suite (final) | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` | **718 passed, 0 failed** (99s) |
| Lint | `ruff check` (all new/changed) | clean |
| Types | `mypy frontier_scout/agent_firewall/` | **0 errors in new code** (pre-existing errors remain in `store.py`/`packs.py`/`evaluate.py`, none CI-gated) |
| Live E2E | `agent scan → policy init → check(allow/needs_approval/block) → receipts → export` on temp repos | works; **no secret leak**; traversal rejected |

## 6. Known limitations

- **Advisory, not enforcement.** `block`/`needs_approval` are *output*; Frontier Scout prevents nothing at
  runtime. (By design — see non-goals.)
- **Heuristic capability detection.** `agent check` classifies task text with deterministic regex
  (`mcp_audit`); it can miss obfuscated intent or over-flag a benign mention. It fails closed (unknown →
  approval), but it is a heuristic, not a proof.
- **`check --json` stdout** echoes the user's own just-typed task/paths unredacted (the *durable* receipt is
  redacted); noted in the security review.
- **MCP-server-reference detection** in `check` is name-substring based and `mcp_server_allowlist` defaults
  empty (deny-by-default) — practical but coarse.
- **CI gating gap:** the MVP's tests ride the broad pytest step (gated), but `make lint/type/coverage` still
  target only the parked `platform/*` tree, so the MVP code is **not** lint/type/coverage-gated in CI unless
  those Makefile globs are widened (deferred; we ran ruff/mypy locally instead — see §5). Not claimed as
  "CI-gated."
- **Unvalidated.** Zero design-partner sessions (see §9).

## 7. Security caveats

A Phase-6 adversarial multi-agent review (5 dimensions, verified findings) found and **fixed 6 issues** (2
HIGH: a fail-OPEN policy loader and a `show_receipt` path traversal; plus redaction asymmetry, exporter
short-token gap, unbounded read, fail-closed coverage) — all pinned by `tests/test_agent_security.py`. Full
write-up: [`security-review.md`](security-review.md). Residual caveats: advisory-only; stdout echo of user
input; not a compliance control; **not enterprise-grade / not complete protection / research preview**. The
package never executes the proposed task, never runs an MCP server, never reaches the network, and never
reads secret file contents.

## 8. Stale surfaces deprecated or deferred

- **"Adoption Firewall" name clash** disambiguated (DEPRECATIONS.md): the legacy radar slice
  (`evaluate`/`trial`/`guard`/`policy`, TOML, *executes*) is left untouched and de-emphasized; the new static
  `agent` group is the agent-governance surface going forward.
- **pyproject** description refreshed off the drifted "AI adoption radar" line; `tech-radar` →
  `agent-governance` keyword.
- **Deferred (out of scope, untouched):** `platform/*` + `incident_change_scout` (parked, experimental-gated),
  `tui*`/`report.py`/`providers/`/`wizard/`/`lab.py` (radar engine), `RELEASE_NOTES.md` + `docs/release-metadata.md`
  metadata drift (release-time artifacts — flagged, not rewritten this sprint).

## 9. Next 7-day roadmap

**The bottleneck is validation, not features.** Both the strategy memo and the prior sanctioned-packs pivot
note carry a standing rule: *don't build V1 — earn the next build with real, workflow-shaped pull.* So the
next week is about **proving the artifact with real people**, not more code:

1. Run `agent scan`/`policy init`/`check` on **3–5 real repos** (one frontend, one service, one monorepo) and
   eyeball whether the generated policy + decisions are better than manual curation.
2. Put the gold-path example + a 2-minute demo in front of **5 design partners** (platform/AppSec leads); ask
   the falsifying question: *"would you route a real agent task through this instead of a Slack/manual review?"*
3. Capture the signal (which artifact they keep — policy, receipt, or snippet). **0/5 sessions done.**
4. Only-if-trivial code polish: widen `make lint`/`make type` globs to include `frontier_scout/agent_firewall/`;
   add a one-line `agent scan --strict` CI recipe to the README.

## 10. Next 30-day roadmap (build only on validated pull)

- If partners keep the **policy**: a second export target (GitHub repo ruleset / CODEOWNERS-style, or Docker
  MCP profile) — the memo's interop wedge.
- If they keep the **receipt**: a `agent check` pre-commit / CI mode that writes a receipt and gates a PR
  (still advisory; non-blocking notifier first).
- If they keep the **decision**: an explicit `allowed_capabilities` field so a team can intentionally relax a
  gate (today every dangerous flag fails closed).
- A real JSON schema doc for `frontier-scout.policy.json` + receipts.
- **Not** building (per memo non-goals): hosted SaaS, runtime enforcement, behavioral MCP sandbox, Jira/Linear,
  TUI expansion, PM-replacement.

## 11. Exact next prompt to give Claude Code / Codex

> **Do not build new features yet — validation is the gate.** First, dogfood the agent firewall on 3 real
> repos and write `docs/strategy/agent-firewall-dogfood.md` with: for each repo, the `agent scan` surface
> counts, whether the generated `frontier-scout.policy.json` needed hand-editing, and 3 `agent check` results
> that surprised you (false allow / false block). Then make exactly ONE small, validation-supporting change:
> widen `make lint` and `make type` in the Makefile to include `frontier_scout/agent_firewall/` so the new
> code is CI-gated, and add a `frontier-scout.policy.json` JSON-schema doc under `docs/`. Keep everything
> static and advisory; do not add runtime enforcement, a second export target, or any new dependency until a
> design partner asks for it. Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` and confirm 718+
> green before committing.

---

### Definition of done — met

A user can install/run Frontier Scout locally → `agent scan` a repo → `agent policy init` (conservative
policy) → `agent check "<task>"` (allow/needs_approval/block) → `agent receipts show` → read a README
explaining the new product and its non-claims → run `pytest` for the core behavior (46 new tests, 718/0). All
honesty invariants hold; the security review's HIGH findings are fixed. **Shipped as a research preview;
validation is the explicit next step.**
