# Contributing

PRs are welcome. Keep them small, testable, and grounded in the local-first
CLI architecture.

This is a small-maintainer alpha project. Be direct, kind, and specific:
criticize behavior and code, not people; assume good intent; and keep security
details out of public issues.

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

- **CLI/report improvements** that reduce time-to-wow without adding a hosted dependency.
- **Source additions** in `scripts/scout.py` with clear quota/rationale notes.
- **Validator hardening** in `scripts/validators.py` with regression tests.
- **Lab safety improvements** in `scripts/lab_runner.py` that preserve hermetic subprocess execution.
- **Adoption Firewall improvements** to `evaluate`, `trial`, `guard`, policy rules, permission manifests, and receipt rendering.
- **Documentation fixes** that keep README, ROADMAP, SECURITY, and AGENTS aligned.

## What gets pushback

- Hosted SaaS, accounts, central telemetry, or multi-tenant sync.
- Auto-installing recommended tools into a user's real project.
- New LLM vendors without a strong reason and tests around cost/error handling.
- Bypassing `scripts/validators.py` before writing verdicts.
- Passing `os.environ` into lab subprocesses.
- Letting `guard` mutate project files or silently approve dangerous capabilities without a stored trial receipt.

## Architecture sketch

```text
sources -> dedupe -> score -> verdict -> optional judge -> validators
       -> SQLite store -> CLI/report/MCP surfaces -> optional lab
       -> evaluate/trial/guard -> local adoption receipts
```

Every Anthropic call routes through `scripts/llm_client.py` with retry and
backoff. Every scan records cost and quality metadata. The public product is
local-first: static reports and SQLite history before plugins or integrations.

## Security issues

Do not file a public issue for vulnerabilities. Use GitHub private
vulnerability reporting when it is enabled for the repository. If private
reporting is unavailable, open a minimal public issue asking for a private
contact path without disclosing details.

## Versioning and release

Use semantic versioning. As of v1.2.1 the release path has two stages:
a tag-driven GitHub Release (automatic, with assets), and a manual
PyPI publish step (`workflow_dispatch`). Splitting them lets us verify
the wheel installs from the GitHub Release before pushing it to PyPI
where it can never be unpublished.

1. Bump `project.version` in `pyproject.toml` and the matching string in
   `frontier_scout/__init__.py`.
2. Add a `## X.Y.Z - YYYY-MM-DD` section to `CHANGELOG.md`. Use the
   same title for the GitHub Release notes.
3. Open a PR on `feat/vX.Y.Z-...`, wait for green CI, resolve any
   CodeRabbit threads, get review count down, admin-merge with
   protections temporarily lowered if needed, restore protections.
4. Create and push an annotated tag `vX.Y.Z` on the merge commit.

Pushing the tag triggers `.github/workflows/release.yml`, which:

- builds wheel and sdist,
- creates a GitHub Release using the matching `CHANGELOG.md` section
  and attaches the wheel + sdist as assets.

The PyPI publish job is gated on `workflow_dispatch` so it stays
manual. After confirming the GitHub Release looks right (assets
present, notes correct), trigger the `Release` workflow manually with
`workflow_dispatch` to publish to PyPI via trusted publishing (OIDC,
configured in `release.yml`). v1.2.1 is the first PyPI release in the
v1.2 line — v1.2.0 stayed GitHub-only.
