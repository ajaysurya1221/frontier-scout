# CLAUDE.md — Frontier Scout

**Read `AGENTS.md` first** (repo layout, run/test commands, conventions, definition of
done, "ask before changing"). This file is the quick-load companion: the current facts an
agent needs before touching the code.

## What this is

Frontier Scout — a **policy compiler + PR scope verifier** for AI coding agents, **Claude
Code first**. It compiles a typed repo policy (`frontier-scout.policy.json`) into Claude
Code's **native** controls (settings `permissions` + hooks), the hook writes **action
receipts**, and a CI verifier checks that a PR's diff stayed within the approved scope.
Keyless, offline; the only runtime dependency is `pydantic`. Python 3.11+, setuptools, PyPI.

**Research preview — technically coherent, not market-validated.** No PMF / adoption claim.

> **2.0.0 was a hard pivot.** The former adoption radar, sanctioned-MCP-packs product,
> Mission Control TUI, `platform/` runtime substrate, LLM providers, SQLite store, and
> scheduling were all **removed**. If older notes/memories mention `scout`/`packs`/`tui3`/
> `platform`/`providers`/`store`, treat them as historical — verify against current code.

## Working principles

Skim **AGENTS.md → Working principles** (think before coding · simplicity first · surgical
changes · goal-driven) before editing.

## The product surface

The CLI is `frontier-scout agent <verb>` (+ `doctor`). Bare `frontier-scout` prints help.

- `agent compile [--target claude] [--repo .] [--out .]` — compile the policy into
  `.claude/settings.json` (a `permissions` allow/deny/ask block), `.claude/hooks/`
  (`pre_tool_use.py` / `post_tool_use.py` + a **self-contained stdlib** `_fs_guard.py`),
  `policy.lock.json` (sha256 of the policy), a managed MCP allow/deny fragment, and
  `.github/workflows/frontier-scout-verify.yml`.
- `agent verify-pr [--base <ref>] [--receipts <glob>] [--advisory]` — **fail-closed** PR
  check: read-only `git diff` vs. receipts + lock. Flags protected-path changes without a
  receipt, policy drift since compile, stale receipt hashes, and deny-bypasses. Emits
  `::error::`/`::warning::` GitHub annotations; exit non-zero on violation.
- `agent scan` · `agent policy init|explain` · `agent check "<task>"` (static pre-check,
  executes nothing, exit `0/3/4`) · `agent receipts list|show` · `agent export
  agents-md|pr-checklist` (advisory snippets). `agent export claude` points to `compile`.
- `doctor` — offline readiness check (policy/lock/settings/hooks/workflow/drift).

**Key modules** (`frontier_scout/agent_firewall/`): `models` (`AgentPolicy`, `TaskDecision`,
`Receipt`) · `policy` (load/generate/save, fail-closed defaults) · `scan` (risk surfaces;
secret files **by name only**) · `decision` (`evaluate_task`, the static `agent check`) ·
`lock` (`policy_hash`, `policy.lock.json`) · `hook_runtime` (stdlib-only `decide()` +
receipt writers, copied verbatim into a target repo's `_fs_guard.py`) · `compile`
(`compile_claude`) · `verify` (`verify_pr`). Plus `exporters/` (`claude_config.to_managed_config_from_names`,
`policy_snippets`), shared `mcp_audit` (capability taxonomy), `policy.PolicyFinding`/`Severity`,
`safety_summary.RISKY_FLAGS`, and `outputs/_text.scrub_secrets` (redaction).

## This repo dogfoods its own policy

`frontier-scout.policy.json` + `policy.lock.json` + `.claude/settings.json` + `.claude/hooks/`
are committed, so sessions here run under the compiled policy (allow/deny/ask + receipts to
the gitignored `.frontier-scout/receipts/`). Normal dev is allowed; CI config, secrets, and
the guardrails themselves (policy/lock/hooks) are approval-gated; the `gitnexus` MCP is
allowlisted (other MCP servers are denied). Change it via edit → `agent compile` → commit.
The CI verify workflow runs **`--advisory`** (warn-only) while onboarding.

## Honesty invariants (load-bearing — keep copy *and* behavior aligned)

- **Emit, don't enforce.** Frontier Scout writes native config; **Claude Code** (hooks +
  permissions) enforces locally and **GitHub Actions** enforces in CI. We never build a
  runtime, sandbox, MCP gateway, policy language, or signed ledger — we compile to / verify
  the wheels that exist.
- **Don't own the receipt layer.** We never build a signed receipt protocol, signing daemon,
  receipt SDK, MCP receipt proxy, or dashboard. Local receipts are control evidence for PR
  scope verification, not a portable receipt standard — the external Agent Receipts project
  owns that space, so we integrate rather than reinvent.
- **Static + read-only.** The scan reads file *names*, never secret *contents*. The only
  subprocess is a read-only `git diff` (verify-pr) / `git rev-parse` (receipt metadata).
- **Fail-closed.** Missing/malformed policy denies by default; dangerous capabilities
  escalate to approval; a non-empty protected diff with no receipts fails the PR.
- **Control evidence, not a guarantee.** Local hooks are not a complete enforcement
  boundary — they are deliberately paired with the CI diff verifier. Never overclaim.
- **Don't rely on optional runtime conveniences.** Frontier Scout does not depend on hook
  input-rewriting or mid-session settings reload — even where current Claude Code supports
  `updatedInput` in hook decisions and live reload of most permissions/hooks settings.
  Correctness comes from deterministic compile output, receipts, and CI verification, not
  from those conveniences (so don't write that Claude Code "cannot" do them).
- **Redacted.** Every persisted/emitted string runs through `scrub_secrets`.
- **Claude Code first.** Codex/Cursor/Copilot are roadmap, not built.

The `hook_runtime.py` module **must stay stdlib-only** (no `frontier_scout` imports) — the
compiler copies it verbatim into a user repo where the package may not be installed. A
golden test (`test_agent_compile.py`) asserts the copy is byte-identical and runs the
generated hook as a subprocess.

## Tests in this environment

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

- In the local conda setup use `/opt/miniconda3/bin/python` (bare `python` may not be on
  PATH). The suite is fast and fully offline now (no TUI/LLM/network tests).
- `make lint` (ruff), `make type` (mypy `--strict` over `agent_firewall` + `exporters`),
  `make coverage`, `make audit` (pip-audit + bandit), `make demo` (offline compile+doctor
  in a temp dir).

## Packaging gotcha (load-bearing)

The compiler copies `frontier_scout/agent_firewall/hook_runtime.py` into a target repo's
`.claude/hooks/_fs_guard.py`, so the **wheel must ship that file** (it's `.py`, so the
default setuptools package discovery includes it). `release.yml` has a guard asserting the
built wheel bundles `hook_runtime.py`. (The former `.tcss`/`package-data` gotcha is gone
with the TUI.)

## Release process

1. Bump `version` in `pyproject.toml` + `frontier_scout/__init__.py`; add a `CHANGELOG.md`
   `## X.Y.Z - <date>` entry (the release workflow extracts that exact heading).
2. PR → CI (full suite + `detect-secrets --all-files` + CodeQL). Mark genuine secret-scan
   false positives with `# pragma: allowlist secret`.
3. `main` is protected (1 review + `enforce_admins` + conversation-resolution,
   **squash-only**): merge via relax→merge→restore — PATCH `required_approving_review_count`
   1→0, squash (`gh pr merge --squash --admin`), then →1 (**always restore**).
4. Tag `vX.Y.Z` → `release.yml` publishes the GitHub Release (draft→publish) + PyPI (trusted
   publishing, gated by the `pypi` deployment environment — approve the pending deployment).
5. Verify the built wheel bundles `agent_firewall/hook_runtime.py`.
6. **Never reuse a burned version:** GitHub immutable-releases permanently reserve a deleted
   release's tag — bump to the next patch instead.
7. After the release is green, move the floating Action major tag: `git tag -f v2 vX.Y.Z &&
   git push -f origin v2` (the release trigger matches full semver only, so this fires
   nothing; no Release object → immutable-tag reservation doesn't apply).
8. One-time per major: publish the Action to the Marketplace (edit the published release →
   "Publish this Action to the GitHub Marketplace").

## Security / conventions

See `AGENTS.md` → "Conventions" and "Ask before changing". Load-bearing: emit not enforce;
static + read-only (names not contents); fail-closed; redact every emitted string; never
auto-install; receipts are evidence not proof; don't read `.env.local`.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **frontier-scout**. Use the GitNexus MCP tools to
understand code, assess impact, and navigate safely.

> The index is stale after the 2.0.0 deletion sweep — run `npx gitnexus analyze` first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level).
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping.
- For full context on a symbol — callers, callees, flows — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource                                        | Use for                                  |
| ----------------------------------------------- | ---------------------------------------- |
| `gitnexus://repo/frontier-scout/context`        | Codebase overview, check index freshness |
| `gitnexus://repo/frontier-scout/clusters`       | All functional areas                     |
| `gitnexus://repo/frontier-scout/processes`      | All execution flows                      |
| `gitnexus://repo/frontier-scout/process/{name}` | Step-by-step execution trace             |

## CLI

| Task                                         | Read this skill file                                        |
| -------------------------------------------- | ----------------------------------------------------------- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md`       |
| Blast radius / "What breaks if I change X?"  | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?"             | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md`       |
| Rename / extract / split / refactor          | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md`     |
| Tools, resources, schema reference           | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md`           |
| Index, status, clean, wiki CLI commands      | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md`             |

<!-- gitnexus:end -->
