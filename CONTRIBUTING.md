# Contributing

PRs are welcome. Keep them small, testable, and grounded in the local-first CLI architecture.

Frontier Scout is a **policy compiler + PR receipt verifier** for AI coding agents (Claude
Code first): it compiles a typed repo policy into the agent's native controls (settings
`permissions` + hooks), the hook writes action receipts, and a CI verifier checks a PR's diff
against the approved scope. Keyless and offline; the only runtime dependency is `pydantic`. A
small-maintainer **research preview** (technically coherent, not market-validated) — make no
PMF / adoption claim.

Honesty invariants any change must respect:

- **Emit, don't enforce.** The compiler (`agent_firewall/compile.py`, `exporters/`) **emits**
  native config; Claude Code (hooks + permissions) and GitHub Actions enforce it. Never build
  a runtime, sandbox, MCP gateway, policy language, or signed ledger.
- **Static + read-only.** The scan reads file *names*, never contents; the only subprocess is
  a read-only `git diff` / `git rev-parse`.
- **Fail-closed** and **redacted** (`scrub_secrets`). Output is **control evidence, not a
  guarantee**.
- **Claude Code first; Codex / Cursor / Copilot are roadmap**, not built.

Be direct, kind, and specific: criticize behavior and code, not people; assume good intent;
keep security details out of public issues.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a PR

```bash
python -m compileall outputs tests frontier_scout
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
make lint    # ruff
make type    # mypy --strict over agent_firewall + exporters
make audit   # pip-audit + bandit
make demo    # offline compile + doctor in a temp dir
```

Also verify the top-level docs (`README.md`, `AGENTS.md`, `CLAUDE.md`, and `ROADMAP.md` /
`CHANGELOG.md` when relevant) still match any user-visible change.

## What lands fast

- **Compiler / verifier improvements** to `agent_firewall/` (`compile`, `verify`, `lock`,
  `hook_runtime`, `decision`, `scan`, `policy`, `models`) and `exporters/`, with tests, that
  keep the tool emit-only, static, and fail-closed.
- **New compile targets** (Codex, later Cursor/Copilot) that reuse the same typed policy —
  discuss first (see AGENTS.md § Ask before changing).
- **Stronger evidence** — attested receipts via existing attestation tooling, or scanner
  findings (CodeQL/Dependabot/Semgrep) as policy inputs.
- **Documentation fixes** that keep README, ROADMAP, SECURITY, AGENTS, and CLAUDE.md aligned.

## What gets pushback

- A new agent runtime, sandbox, general MCP gateway, custom policy language, custom telemetry
  format, or signed ledger — compile to / verify the wheels that exist.
- Framing the compiled config or `verify-pr` as a guarantee of safety (it is control
  evidence; local hooks are paired with the CI verifier on purpose).
- A subprocess beyond the read-only `git` calls; reading secret *contents*; auto-installing
  anything; hosted SaaS / accounts / central telemetry / multi-tenant sync.
- Claiming an unbuilt surface (Codex/Cursor/Copilot) is shipped.

## Architecture sketch

```text
frontier-scout.policy.json (typed AgentPolicy)
   -> agent compile  -> .claude/settings.json (permissions) + .claude/hooks/ (decide + receipts)
                      + policy.lock.json (sha256) + managed MCP fragment + verify workflow
   -> (Claude Code runs; hook writes receipts to .frontier-scout/receipts/)
   -> agent verify-pr -> read-only git diff vs. receipts + lock -> fail-closed verdict + PR annotations
```

This repo **dogfoods** its own policy (`frontier-scout.policy.json` + `.claude/` are
committed), so sessions here run under the compiled controls.

## Security issues

Do not file a public issue for vulnerabilities. Use GitHub private vulnerability reporting
when enabled. If unavailable, open a minimal public issue asking for a private contact path
without disclosing details. See `SECURITY.md`.

## Versioning and release

Semantic versioning; releases are **tag-driven** (push a `vX.Y.Z` tag to publish). See
AGENTS.md § Release and CLAUDE.md § Release process for the authoritative checklist:

1. Bump `version` in `pyproject.toml` **and** `frontier_scout/__init__.py`; add a
   `CHANGELOG.md` `## X.Y.Z - <date>` entry.
2. Open a PR. CI runs the full non-live suite + `detect-secrets --all-files` + CodeQL. Mark
   genuine secret-scan false positives with `# pragma: allowlist secret`.
3. Merge: `main` is protected (1 review + `enforce_admins` + conversation-resolution,
   squash-only). Use the relax→merge→restore dance on `required_approving_review_count`
   (1 → 0 → 1; always restore), squashing with `gh pr merge --squash --admin`.
4. Tag `vX.Y.Z` and push it. `release.yml` builds the wheel + sdist, publishes the GitHub
   Release, and publishes to PyPI (trusted publishing, gated by the `pypi` deployment
   environment — approve the pending deployment). The wheel must bundle
   `agent_firewall/hook_runtime.py` (release.yml guards this).
5. **Never reuse a burned version:** immutable releases reserve a deleted tag — bump instead.
