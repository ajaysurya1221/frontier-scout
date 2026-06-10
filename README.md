<div align="center">

<img src="https://raw.githubusercontent.com/ajaysurya1221/frontier-scout/main/docs/assets/frontier-scout-banner.png" alt="Frontier Scout — PR scope verifier + policy compiler for AI coding agents (Claude Code first)" width="100%">

<p>
  <strong>Verify in CI that an AI agent's PR stayed within approved scope — fail-closed, with signed evidence.</strong><br>
  <sub>A GitHub Action for the verify side · a policy compiler into native Claude Code controls for the authoring side.</sub>
</p>

<p>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square">
  <img alt="Research preview" src="https://img.shields.io/badge/status-research%20preview-orange?style=flat-square">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  <img alt="No telemetry" src="https://img.shields.io/badge/telemetry-none-lightgrey?style=flat-square">
</p>

<p>
  <a href="#quickstart-the-github-action">Quickstart</a> ·
  <a href="#whats-verified-vs-whats-claimed">Verified vs claimed</a> ·
  <a href="#the-policy">Policy</a> ·
  <a href="#cli">CLI</a> ·
  <a href="#safety-model">Safety model</a> ·
  <a href="KILL_CRITERIA.md">Kill criteria</a>
</p>

</div>

> **Research preview — technically coherent, not market-validated.** No PMF / adoption
> claim; this project is demand-gated with **public kill criteria** ([KILL_CRITERIA.md](KILL_CRITERIA.md)).
> Claude Code first (Codex/Cursor/Copilot are roadmap). Frontier Scout **emits** native
> config and **verifies** evidence — Claude Code and GitHub Actions do the enforcing. Its
> output is **control evidence, not a guarantee** that no unsafe action occurred.

## The problem

Agent pull requests are saturating human review. Teams want agents to keep shipping —
without handing them unconstrained repo, shell, network, and MCP access, and without
rubber-stamping diffs nobody can afford to read line by line.

Code review tools judge the *content* of a change. Nothing in CI answers the *mandate*
question: **did this change stay inside what the agent was approved to touch, and is there
evidence of what actually ran?** That's Frontier Scout: a fail-closed scope verifier for
agent PRs, plus a compiler that turns one typed policy into the agent's native controls.

## Quickstart: the GitHub Action

Add the verifier to any repo with a `frontier-scout.policy.json` (one `policy init` away —
see [full setup](#full-setup-policy--local-hooks)):

```yaml
name: Frontier Scout verify
on:
  pull_request:
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # the verifier diffs against the base ref
          persist-credentials: false
      - uses: ajaysurya1221/frontier-scout@v2.1.0
        with:
          advisory: "true"          # onboarding posture: warn, don't block. Drop for a hard gate.
          evidence-artifact: "frontier-scout-evidence"
```

The Action runs `agent verify-pr` **fail-closed**: it exits non-zero when a protected path
changed without an action record, the policy drifted from its lock, a record's hash is
stale, an action ran despite a `deny` — or when the diff itself can't be computed
(**UNVERIFIED is never reported as a pass**). It annotates the PR, writes a step summary,
and emits a machine-readable evidence JSON.

### Signed evidence (optional)

With `attest: "true"`, the evidence JSON is signed via [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
(Sigstore) — Frontier Scout deliberately rides GitHub's signing rail rather than inventing
a receipt protocol:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
steps:
  - uses: ajaysurya1221/frontier-scout@v2.1.0
    with:
      attest: "true"
      evidence-artifact: "frontier-scout-evidence"
```

Anyone can then verify the evidence independently:

```bash
gh attestation verify frontier-scout-evidence.json --owner <org-or-user> \
  --predicate-type https://github.com/ajaysurya1221/frontier-scout/predicate/verify-pr/v1
```

If attestation is requested and cannot be produced, the Action **fails** — it never
silently degrades to unsigned evidence. (Not available to fork PRs; OIDC.)

## What's verified vs what's claimed

Honesty model, load-bearing:

| Artifact | Status |
|---|---|
| Diff-vs-policy scope check (CI re-derives the diff itself) | **Verified** — computed from the repo, fail-closed |
| Evidence JSON **with** a passing `gh attestation verify` | **Verified** — signed by the workflow's Sigstore identity, mode (`enforcing`/`advisory`) carried in the predicate |
| Evidence JSON without attestation | **Supporting claim** |
| Local action records (receipts written by the agent-side hook) | **Supporting claim** — written on the same machine the agent controls |
| `UNVERIFIED` (diff not computable) | **Never** rendered as a pass, in either mode |

## Full setup (policy + local hooks)

```bash
pip install frontier-scout

cd your-repo
frontier-scout agent policy init          # conservative frontier-scout.policy.json from a scan
frontier-scout agent compile --target claude --repo . --out .
frontier-scout doctor                      # confirm policy/lock/hooks/workflow are in place
```

`compile` writes:

| Artifact | Purpose |
|---|---|
| `.claude/settings.json` | `permissions` (allow/deny/ask) + hook wiring |
| `.claude/hooks/pre_tool_use.py` · `post_tool_use.py` | decide allow/deny/ask, write action records |
| `.claude/hooks/_fs_guard.py` | self-contained (stdlib-only) decision + record logic |
| `policy.lock.json` | sha256 binding action records to this exact policy |
| `managed-settings.json` | admin/MDM MCP allow/deny fragment |
| `.github/workflows/frontier-scout-verify.yml` | the PR verifier check |

Run Claude Code normally — the hook gates each tool call and writes redacted local action
records to `.frontier-scout/receipts/`. The CI verifier then checks the PR diff against the
policy lock and those records. The CLI equivalent of the Action:

```bash
frontier-scout agent verify-pr --repo . --base "origin/main" \
  --receipts "frontier-scout-receipts/*.json" --json-out evidence.json
```

See [`examples/demo-walkthrough.md`](examples/demo-walkthrough.md) for a 90-second
fail-closed demo, and [`examples/sample-repo/`](examples/sample-repo/) for the end-to-end
fixture.

## The policy

`frontier-scout.policy.json` is a typed schema (not a new language), compiled to native
config — four dimensions plus approval gates:

```json
{
  "allowed_shell_commands": ["pytest", "git status"],
  "blocked_shell_commands": ["rm -rf", "git push --force"],
  "allowed_file_globs": ["src/**", "tests/**"],
  "protected_file_globs": ["**/migrations/**", ".github/workflows/**", "**/.env"],
  "mcp_server_allowlist": ["github"],
  "required_checks": ["pytest"],
  "approval_gates": ["network", "shell", "credential", "write", "protected-path"]
}
```

Decisions are **fail-closed**: anything not provably safe escalates to `ask`; off-allowlist
MCP servers and blocked commands hard-`deny`.

## CLI

| Command | What it does |
|---|---|
| `agent verify-pr` | Fail-closed PR check: action records + diff vs. the locked policy (`--json`, `--json-out`) |
| `agent compile` | Compile the policy into Claude Code native controls + CI verifier |
| `agent scan` | Static repo agent-risk scan (secret-likely files by name only) |
| `agent policy init \| explain` | Generate / read a conservative policy |
| `agent check "<task>"` | Static pre-check of a proposed task (executes nothing) |
| `agent receipts list \| show` | Inspect local action records |
| `agent export agents-md \| pr-checklist` | Advisory policy snippets |
| `doctor` | Offline agent-readiness check |

## Safety model

- **Static + read-only.** The scan reads file *names*, never secret *contents*. The only
  subprocess is a read-only `git diff` in `verify-pr`.
- **Emit, don't enforce.** Frontier Scout writes native config; Claude Code's hook/permission
  system enforces locally and GitHub Actions enforces in CI.
- **Fail-closed.** A missing/malformed policy denies by default; every dangerous capability
  escalates to approval; a non-empty protected diff without action records fails the PR; an
  uncomputable diff is UNVERIFIED, never PASS.
- **Redacted.** Every persisted/emitted string is scrubbed of secret-shaped tokens.
- **Honest.** It is control evidence, not a guarantee. Local hooks are not a complete
  enforcement boundary — they are paired with the CI diff verifier on purpose, and unsigned
  evidence is always labeled a claim (see [verified vs claimed](#whats-verified-vs-whats-claimed)).
  Correctness comes from deterministic compile output, action records, and CI verification —
  Frontier Scout does not rely on optional Claude Code conveniences like hook input-rewriting
  or mid-session settings reload (even where current Claude Code supports them).

## What we don't build

Frontier Scout writes **local action records** for PR scope verification and signs evidence
**through GitHub's attestation rail**. It is **not** a signed receipt protocol, signing
daemon, MCP proxy, SDK, dashboard, or ledger. It deliberately reuses wheels that already
exist:

- **Claude Code** — runtime hooks, permissions, and managed settings (local enforcement).
- **GitHub Actions** — the PR check (CI enforcement).
- **GitHub artifact attestations / Sigstore** — evidence signing and verification.
- **MCP clients / gateways** — tool transport.
- **Existing receipt / provenance projects** (for example, Agent Receipts or Pipelock) —
  for any future portable receipt format; integrate, don't reinvent.

## Roadmap

P0 (shipped): the GitHub Action with signed evidence, the Claude compiler + local action
records, the CI verifier. P1 is **demand-gated** (see [KILL_CRITERIA.md](KILL_CRITERIA.md)):
platform-evidence ingestion, Codex adapter, scanner findings as policy inputs — built only
when a named design partner asks. See [ROADMAP.md](ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md). Tests:
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`. Lint/type: `make lint`, `make type`.

## License

MIT — see [LICENSE](LICENSE).
