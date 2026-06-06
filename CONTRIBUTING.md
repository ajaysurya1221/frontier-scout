# Contributing

PRs are welcome. Keep them small, testable, and grounded in the local-first
CLI architecture.

The headline product is **sanctioned MCP-server packs for coding assistants
(Claude Code first)**: repo-rank approved MCP servers into a **static** capability +
policy safety map, then **export a Claude Code managed-config fragment**
(`allowedMcpServers` / `deniedMcpServers` + a project `.mcp.json`) an admin deploys.
The local-first **adoption radar** (scout / evaluate / dossier / lab / trial / guard /
policy / report + the Mission Control TUI) is the **engine underneath** that powers
ranking and the safety map — not the headline. This is a small-maintainer **research
preview** (technically coherent, not market-validated): make no PMF / adoption claim.

Honesty invariants any change must respect:

- **Static-only.** The pack flow (`packs.py`, `pack_flow.py`, `safety_summary.py`)
  **never executes** an MCP server — capability + policy classification only.
- **Emit, don't enforce.** The exporter (`exporters/claude_config.py`) **emits** an
  admin-applied config fragment; it does **not** enforce runtime policy or auto-deploy.
- **Claude Code first; Copilot / Cursor / Docker are roadmap**, not built.

Be direct, kind, and specific: criticize behavior and code, not people; assume good
intent; and keep security details out of public issues.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
cp .env.example .env  # optional; only needed for live scans
```

## Before opening a PR

```bash
python -m compileall scripts outputs tests frontier_scout
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
frontier-scout demo
frontier-scout scan --dry-run
detect-secrets scan --all-files --force-use-all-plugins
```

## What lands fast

- **Sanctioned-pack improvements** to the static flow — `packs.py` (candidate
  discovery / repo-ranked rows), `pack_flow.py` (candidates → safety → sanction →
  export), `safety_summary.py` (the static capability + policy map), and
  `exporters/claude_config.py` (the Claude managed-config fragment) — that keep the
  flow static and the export admin-reviewable, with tests.
- **Proof + signal tooling** — `proof_variants.py` (the A/B/C variants behind
  `packs proof`) and `telemetry.py` (the opt-in funnel behind `frontier-scout stats`)
  — that sharpen design-partner validation without leaking source content.
- **CLI/report improvements** that reduce time-to-wow without adding a hosted dependency.
- **Source additions** in `scripts/scout.py` with clear quota/rationale notes.
- **Validator hardening** in `scripts/validators.py` with regression tests.
- **Lab safety improvements** in `scripts/lab_runner.py` that preserve hermetic subprocess execution.
- **Adoption Firewall (radar engine) improvements** to `evaluate`, `trial`, `guard`, policy rules, permission manifests, and receipt rendering.
- **Documentation fixes** that keep README, ROADMAP, SECURITY, AGENTS, and CLAUDE.md aligned.

## What gets pushback

- Hosted SaaS, accounts, central telemetry, or multi-tenant sync.
- Auto-installing recommended tools (or sanctioned MCP servers) into a user's real project.
- **Executing an MCP server in the pack flow** — sanctioning is static-only; any
  runtime probe is roadmap and lives in the hermetic lab, not the pack path.
- **Framing the export as runtime enforcement** — it emits an admin-applied fragment,
  it does not grant runtime permissions or auto-deploy.
- **Claiming an unbuilt surface is done** — Copilot / Cursor / Docker export, and a
  behavioral MCP probe, are roadmap; don't present them as shipped.
- New LLM vendors/providers without a strong reason and tests around cost/error handling.
- Bypassing `scripts/validators.py` before writing verdicts.
- Passing `os.environ` into lab subprocesses.
- Letting `guard` mutate project files or silently approve dangerous capabilities without a stored trial receipt.

## Architecture sketch

```text
# the sanctioned-packs product (the headline) — static, no server executed
candidates (packs.py) -> static safety map (safety_summary.py)
       -> risk-gated sanction (pack_flow.py) -> managed-config export (exporters/claude_config.py)
       -> proof variants (proof_variants.py) + opt-in funnel (telemetry.py)

# the radar engine underneath — what powers ranking + the safety map
sources -> dedupe -> score -> verdict -> optional judge -> validators
       -> SQLite store -> CLI/report/MCP surfaces -> optional hermetic lab
       -> evaluate/trial/guard -> local adoption receipts
```

All LLM calls go through the provider abstraction in `frontier_scout/providers/`:
pin exactly one backend with `--provider anthropic|openai|claude-cli|codex-cli`
(`--demo`/offline and the sanctioned-pack flow need none). Availability
deep-probes `<cli> --version` (cached), so a broken-but-on-PATH CLI is skipped,
not silently selected. (The mature engine modules under `scripts/` still carry the
legacy `scripts/llm_client.py` retry/backoff helper.) Every scan records cost and
quality metadata. The public product is local-first: a static export and SQLite
history before plugins or integrations.

## Security issues

Do not file a public issue for vulnerabilities. Use GitHub private
vulnerability reporting when it is enabled for the repository. If private
reporting is unavailable, open a minimal public issue asking for a private
contact path without disclosing details.

## Versioning and release

Use semantic versioning. Releases are **tag-driven** — pushing a `vX.Y.Z` tag is
what publishes; there is no `workflow_dispatch` PyPI step. (See AGENTS.md § Release
and CLAUDE.md § Release process for the authoritative checklist; this mirrors them.)

1. Bump `version` in `pyproject.toml` **and** the matching string in
   `frontier_scout/__init__.py`, and add a `CHANGELOG.md` entry.
2. Open a PR. CI `test` runs the full non-live suite, a `detect-secrets --all-files`
   secret scan, and CodeQL. Mark genuine secret-scan false positives with
   `# pragma: allowlist secret`.
3. **Merge.** `main` is protected (1 review + `enforce_admins` +
   conversation-resolution, **squash-only**). Merge via the relax→merge→restore
   dance: PATCH `required_approving_review_count` 1 → 0, squash with
   `gh pr merge --squash --admin`, then restore it 0 → 1 (**always restore**).
4. **Tag** `vX.Y.Z` on the merge commit and push it. `.github/workflows/release.yml`
   builds the wheel + sdist, publishes the GitHub Release (draft → publish), and
   publishes to PyPI via trusted publishing — gated by the `pypi` deployment
   environment, so you must approve the pending deployment for PyPI to go out.
5. Non-`.py` data (the Textual `tui3/theme.tcss` stylesheets) **must** be declared in
   `[tool.setuptools.package-data]` (`"*" = ["*.tcss"]`) + `MANIFEST.in`, or the
   installed TUI crashes on launch with a `StylesheetError`. Verify the **built wheel**
   bundles the `.tcss` (`release.yml` guards this).
6. **Never reuse a burned version:** GitHub immutable-releases permanently reserve a
   deleted release's tag name — bump to the next patch instead.
