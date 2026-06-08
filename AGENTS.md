# AGENTS Guide

Frontier Scout: a **policy compiler + PR receipt verifier** for AI coding agents (**Claude
Code first**). Compile a typed repo policy into the agent's native controls (settings +
hooks), the hook writes action receipts, and a CI verifier checks a PR's diff against the
approved scope. Local, keyless, offline; the only runtime dependency is `pydantic`. A
**research preview** (technically coherent, **not** market-validated). Use this file as the
handoff playbook.

> **2.0.0 was a hard pivot** away from the adoption radar / sanctioned MCP packs / Mission
> Control TUI / `platform/` runtime / LLM providers / SQLite store. Those were removed.
> Ignore older references to them.

## Repo layout

```text
frontier_scout/                # installable CLI package
  cli.py                       # entry point: `agent <verb>` + `doctor` + --version; bare = help
  doctor.py                    # offline agent-readiness check (policy/lock/hooks/drift)
  mcp_audit.py                 # capability taxonomy (read/write/network/shell/credential/...)
  policy.py                    # shared PolicyFinding + Severity (finding shape)
  safety_summary.py            # RISKY_FLAGS (high-risk capability set)
  agent_firewall/              # the product
    models.py                  #   AgentPolicy, TaskDecision, Receipt
    policy.py                  #   load/generate/save policy (fail-closed defaults)
    scan.py                    #   repo risk surfaces (secret files by NAME only)
    decision.py                #   evaluate_task() — the static `agent check`
    lock.py                    #   policy_hash() + policy.lock.json
    hook_runtime.py            #   STDLIB-ONLY decide() + receipt writers (copied into target repos)
    compile.py                 #   compile_claude(): settings + hooks + lock + workflow
    verify.py                  #   verify_pr(): fail-closed PR check (read-only git diff)
  exporters/
    claude_config.py           #   managed allowedMcpServers/deniedMcpServers from policy names
    policy_snippets.py         #   advisory CLAUDE.md / AGENTS.md / PR-checklist snippets
outputs/_text.py               # scrub_secrets / sanitize_sensitive_text (redaction)
tests/                         # offline regression tests
examples/sample-repo/          # end-to-end demo fixture
docs/                          # docs/spike-claude-config.md pins native config shapes
```

## Local run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cd your-repo
frontier-scout agent policy init                      # -> conservative frontier-scout.policy.json
frontier-scout agent compile --target claude --repo . --out .
frontier-scout doctor                                 # policy/lock/hooks/workflow present?
# (run Claude Code; hooks write receipts to .frontier-scout/receipts/)
frontier-scout agent verify-pr --repo . --base origin/main --receipts "frontier-scout-receipts/*.json"
```

Everything is keyless and offline. The only subprocess is a read-only `git diff` (verify-pr)
/ `git rev-parse` (receipt metadata).

## This repo dogfoods its own policy

Frontier Scout governs **itself**: `frontier-scout.policy.json` + `policy.lock.json` +
`.claude/settings.json` + `.claude/hooks/` are committed, so Claude Code sessions in this
repo are gated by the compiled policy (allow/deny/ask) and write receipts to the gitignored
`.frontier-scout/receipts/`. The policy allows the normal dev surface (edits under
`frontier_scout/**`/`tests/**`/`docs/**`, `pytest`/`ruff`/`mypy`/`make`/`git`/`gh`, the
`gitnexus` MCP) and approval-gates CI config, secrets, and the guardrails themselves
(policy/lock/hooks). To change it: edit `frontier-scout.policy.json`, re-run
`frontier-scout agent compile --repo . --out .`, and commit. The CI verify workflow
(`.github/workflows/frontier-scout-verify.yml`) runs in **`--advisory`** mode (warns, never
blocks) while onboarding; drop `--advisory` to make it a hard gate.

## Test commands

- Full suite: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
  (local conda: `/opt/miniconda3/bin/python`).
- Lint: `make lint` (ruff over `frontier_scout` + `tests`).
- Types: `make type` (mypy `--strict` over `agent_firewall` + `exporters`).
- Coverage: `make coverage`. Audit: `make audit`. Demo: `make demo`.
- Syntax sweep: `python -m compileall outputs tests frontier_scout`.

## Conventions (load-bearing invariants)

- **Emit, don't enforce.** Frontier Scout writes native config; Claude Code (hooks +
  permissions) and GitHub Actions enforce. Never build a runtime, sandbox, MCP gateway,
  policy language, telemetry format, or signed ledger — compile to / verify existing wheels.
- **Static + read-only.** The scan reads file *names*, never secret *contents*.
- **Fail-closed.** Missing/malformed policy denies by default; dangerous capabilities
  escalate to approval; a non-empty protected diff with no receipts fails the PR.
- **Control evidence, not a guarantee.** Local hooks aren't a complete boundary — they are
  paired with the CI diff verifier. No overclaiming in copy or output.
- **`hook_runtime.py` stays stdlib-only.** It is copied verbatim into a user repo's
  `.claude/hooks/_fs_guard.py`; importing `frontier_scout` there would break it. A golden
  test asserts the byte-identical copy and runs the generated hook as a subprocess.
- **Redact everything emitted/persisted** via `outputs/_text.scrub_secrets`.
- **Claude Code first.** Codex/Cursor/Copilot are roadmap, not built.
- **No auto-install; local state stays local.**

## Working principles

Adapted from the [Karpathy coding guidelines](https://github.com/multica-ai/andrej-karpathy-skills) (MIT).

- **Think before coding.** Surface assumptions; push back when a request is ambiguous or wrong.
- **Simplicity first.** Minimum that satisfies the task. YAGNI.
- **Surgical changes.** Touch only what's required; match surrounding style.
- **Goal-driven execution.** Define verifiable success criteria, loop until the Definition of done passes.

## Definition of done

1. `python -m compileall outputs tests frontier_scout` passes.
2. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` passes.
3. `make lint` and `make type` pass.
4. `make demo` compiles + doctors the sample policy cleanly.
5. README, ROADMAP, SECURITY, CONTRIBUTING, **CLAUDE.md, AGENTS.md** match any user-visible change.
6. No secrets or noisy runtime ledgers in the git diff.

## Release

1. Bump `version` in `pyproject.toml` + `frontier_scout/__init__.py`; add a `CHANGELOG.md`
   `## X.Y.Z - <date>` entry.
2. PR → CI (full suite + `detect-secrets --all-files` + CodeQL).
3. `main` is protected (1 review + `enforce_admins` + conversation-resolution, **squash-only**);
   merge via relax→merge→restore on `required_approving_review_count` (1→0→1; always restore),
   squashing with `gh pr merge --squash --admin`.
4. Tag `vX.Y.Z` → `release.yml` publishes GitHub Release (draft→publish) + PyPI (trusted
   publishing, gated by the `pypi` deployment environment — approve the run).
5. The built wheel must bundle `agent_firewall/hook_runtime.py` (release.yml guards this).
6. Never reuse a burned version: immutable releases reserve a deleted tag — bump to next patch.

## Ask before changing

Discuss first before adding: a new compile target / export client (Codex / Cursor / Copilot —
currently roadmap), a new policy dimension, a hosted service or sync feature, any subprocess
beyond the read-only `git` calls, or an auto-install path.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **frontier-scout**. Use the GitNexus MCP tools to
understand code, assess impact, and navigate safely.

> The index is stale after the 2.0.0 deletion sweep — run `npx gitnexus analyze` first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius.
- **MUST run `gitnexus_detect_changes()` before committing** to verify scope.
- **MUST warn the user** on HIGH or CRITICAL risk before proceeding.
- Explore with `gitnexus_query({query: "concept"})`; get symbol context with `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function/class/method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings.
- NEVER rename with find-and-replace — use `gitnexus_rename`.
- NEVER commit without running `gitnexus_detect_changes()`.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/frontier-scout/context` | Codebase overview, check index freshness |
| `gitnexus://repo/frontier-scout/clusters` | All functional areas |
| `gitnexus://repo/frontier-scout/processes` | All execution flows |
| `gitnexus://repo/frontier-scout/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
