# Frontier Scout

**Does this PR stay inside its declared scope?**

Check the diff against the base commit's policy.
Compile the same policy into Claude Code permissions and hooks.

**Status:** research preview. 2.2.0 is the current release and repairs the verifier.
v2.1.0 and earlier have known verification defects. [Release details](#the-previous-release-v210)

**Published regression cases** ([matrix](docs/evaluation/verifier-2026-10-06.md)):
```text
Outside allowed paths -> FAIL
Protected path + unsigned receipt -> UNVERIFIED
```

**Used here:** our own PRs exercise the Action in [advisory CI](.github/workflows/frontier-scout-verify.yml).
The PR can edit that workflow; it is not a trusted merge gate.

**Engineering:** [40-test regression matrix](docs/evaluation/verifier-2026-10-06.md) · [Action isolation tests](tests/test_action_isolation.py)
[Hosted source-install check](.github/workflows/ci.yml) · [Optional attestations](#signed-evidence-optional)

**Boundary:** unsigned receipts cannot authenticate approval. Verified attestations identify a workflow.

[Set up the pinned Action](#quickstart-the-github-action) · [Limits](#safety-model)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ajaysurya1221/frontier-scout/main/docs/assets/hero-dark.svg">
  <img alt="frontier-scout, PR scope verifier and policy compiler. Did this agent PR stay inside the scope declared on its base branch? One typed policy compiles into Claude Code controls; CI checks every PR diff against it. Anything unproven is never a pass. Evidence card: verify-pr reads the policy and lock from the base commit. A path outside allowed_file_globs gives FAIL (exit 1); a protected path backed only by an unsigned receipt gives UNVERIFIED (exit 1); a change within the declared scope gives PASS (exit 0). Source: examples/demo-walkthrough.md. This repository runs the Action on its own PRs in advisory mode." src="https://raw.githubusercontent.com/ajaysurya1221/frontier-scout/main/docs/assets/hero-light.svg" width="100%">
</picture>

[![CI](https://img.shields.io/github/actions/workflow/status/ajaysurya1221/frontier-scout/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/ajaysurya1221/frontier-scout/actions/workflows/ci.yml) [![PyPI: last published release](https://img.shields.io/pypi/v/frontier-scout?style=flat-square&label=PyPI%20%28last%20published%29)](https://pypi.org/project/frontier-scout/) [![MIT License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

## Quickstart: the GitHub Action

Add the verifier to any repo with a `frontier-scout.policy.json` (one `policy init` away —
see [full setup](#full-setup-policy--local-hooks)).

> **Release status.** The repaired verifier and Action described in this section ship in
> release **2.2.0** (`ajaysurya1221/frontier-scout@v2.2.0`; `frontier-scout==2.2.0` on PyPI).
> **v2.1.0** and earlier behave differently and have known defects (see
> [the previous release](#the-previous-release-v210) below). Keep the `pull_request` example
> below advisory: the PR can edit that workflow, so it is not a merge gate.

### Repaired verifier (2.2.0)

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
      - uses: ajaysurya1221/frontier-scout@v2.2.0
        with:
          advisory: "true"          # report only: a pull_request workflow is editable by the PR
          evidence-artifact: "frontier-scout-evidence"
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ajaysurya1221/frontier-scout/main/docs/assets/where-dark.svg">
  <img alt="Where frontier-scout sits, between an agent's pull request and the merge decision. Inputs: the base commit's frontier-scout.policy.json and policy.lock.json, and the candidate PR diff (git diff --name-status -z -M base...HEAD). Local receipts are an unsigned input, reported and never an approval. In CI, agent verify-pr reads the policy and lock from the base commit and checks every changed path against allowed_file_globs and protected_file_globs; the verdict is FAIL, UNVERIFIED or PASS, and anything unproven is never a pass. Outputs: the verdict and an evidence JSON with PR annotations and a step summary, exit 0 only on PASS when enforcing. Attestation is optional: with attest true the evidence JSON is signed through Sigstore, which names the workflow, not the approver. A merge gate must run from a workflow the PR cannot edit. This repository's own PRs run the check in frontier-scout-verify.yml in advisory mode: the verdict is reported and the job exits 0." src="https://raw.githubusercontent.com/ajaysurya1221/frontier-scout/main/docs/assets/where-light.svg" width="100%">
</picture>

The Action runs `agent verify-pr` against the base branch. The policy and lock come from
the base commit, so a PR cannot widen its own scope. Every path the PR changes is checked,
including both ends of a rename, deletions, and mode-only and binary changes. The verdict is
one of three:

- **FAIL**: a path outside `allowed_file_globs`; a protected path with no action record; a
  missing, malformed or drifted policy or lock; a malformed, unbound or stale record; or a
  change made despite a `deny`.
- **UNVERIFIED**: a protected path changed and only unsigned records mention it (receipts
  cannot authenticate an approval, so a human approves it outside the tool), or the diff
  could not be collected.
- **PASS**: none of the above.

Merge the policy and lock before relying on the check. They are read from the base branch,
so the PR that introduces them is reported as `POLICY_LOCK_MISSING`.

UNVERIFIED is never reported as a pass. Every finding carries a reason code, and the output
reports scope and approval provenance separately. The Action annotates the PR, writes a step
summary, and emits a machine-readable evidence JSON. The defect matrix behind this behaviour
is in [`docs/evaluation/verifier-2026-10-06.md`](docs/evaluation/verifier-2026-10-06.md).

The Action never runs Python from the PR checkout: every step runs from `$RUNNER_TEMP` with
isolated Python (`python -I`), and the repository reaches the verifier as an absolute
`--repo` path, so a `pip.py`, `json.py` or `frontier_scout/` at the PR root cannot replace
the installer, the verifier or the output step.

On `pull_request`, GitHub runs the workflow file from the PR, so a PR can edit the verify step
itself. A check that must gate merges has to run from a workflow the PR cannot edit, for
example a required workflow in an organization ruleset pinned to a trusted ref. That is a
prerequisite for gating; installing a repaired release does not by itself turn the
`pull_request` example above into a gate.

> **Inspect the same workflow this repository runs**
>
> On pull requests, the [dogfood workflow](.github/workflows/frontier-scout-verify.yml) runs both the CLI verifier and the composite Action against the base branch. The Action uploads an evidence JSON artifact. Both jobs are advisory: inspect the recorded verdict, because a successful job does not mean the scope verdict passed.
>
> A team requiring merge enforcement must place the check in a workflow the candidate PR cannot modify. Local receipts remain unsigned observations.

### The previous release (v2.1.0)

`ajaysurya1221/frontier-scout@v2.1.0` and `frontier-scout==2.1.0` on PyPI predate the repair
shipped in 2.2.0:

- `verify-pr` has five false acceptance paths: unenforced `allowed_file_globs`, any receipt
  counted as approval, unbound receipts, PR-side policy and receipts, and lossy diff parsing.
- Its Action runs Python from the PR checkout's working directory, so a PR can ship a
  `pip.py` or `json.py` that replaces the installer or rewrites the verdict, exit code and
  evidence before anything is uploaded or attested.

If you use it, use it only as an advisory signal on `pull_request` with `contents: read`:
keep `advisory: "true"`, do not set `attest: "true"`, and do not run it from
`pull_request_target` or any workflow that holds secrets or write permissions.

### Signed evidence (optional)

With `attest: "true"`, the evidence JSON is signed via [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
(Sigstore) — Frontier Scout deliberately rides GitHub's signing rail rather than inventing
a receipt protocol. This needs the repaired Action above (2.2.0 or later): on v2.1.0, PR-supplied Python can run before the evidence is signed.

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
steps:
  - uses: ajaysurya1221/frontier-scout@v2.2.0
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
silently degrades to unsigned evidence. (Not available to fork PRs; OIDC.) Attestation is
off by default, and this repository's own dogfood workflow does not request it.

## What's verified vs what's claimed

Honesty model, load-bearing:

| Artifact | Status |
|---|---|
| Scope check: every changed path (both rename ends, deletions, mode and binary changes) against the base commit's policy and lock | **Checked in CI.** The diff and the policy come from git, not from the PR's own files |
| Approval of a protected-path change | **Not authenticated.** FAIL with no receipt, UNVERIFIED with one, never PASS |
| Evidence JSON **with** a passing `gh attestation verify` | **Verified provenance of the JSON.** Signed by the workflow's Sigstore identity, mode (`enforcing`/`advisory`) and verdict carried in the predicate. It does not show who approved a change |
| Evidence JSON without attestation | **Supporting claim** |
| Local action records (receipts written by the agent-side hook) | **Unauthenticated observation.** Written on the same machine the agent controls; never treated as approval; flagged `RECEIPT_IN_PR` when committed in the PR |
| `UNVERIFIED` (no diff, or a protected change backed only by receipts) | **Never** rendered as a pass, in either mode; non-zero exit when enforcing |

In the [documented README comparison](docs/evaluation/verifier-2026-10-06.md#related-projects-declared-scope-and-evidence-trust), Notari describes signed scope approval; Frontier Scout does not authenticate approval. The comparison is pinned to 2026-10-05 source revisions and does not report execution tests.

> **Status:** research preview, maintained; one maintainer; no adoption claims. Claude Code
> first (Codex/Cursor/Copilot are roadmap, not built). The pre-registered demand gates and
> their day-90 evaluation are public: [KILL_CRITERIA.md](KILL_CRITERIA.md).

## Full setup (policy + local hooks)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install frontier-scout==2.2.0

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

`compile` pins the generated workflow to the version that compiled it
(`frontier-scout==2.2.0` here). A workflow compiled by 2.1.0 or earlier installs the latest
release unpinned, so it picks up 2.2.0 and its stricter verdicts on its next run; recompile it
to pin the version. 2.1.0 itself has the defects listed [above](#the-previous-release-v210).

Run Claude Code normally — the hook gates each tool call and writes redacted local action
records to `.frontier-scout/receipts/`. The CI verifier then checks the PR diff against the
base commit's policy and lock, and reports those records as unsigned observations. Receipts
you commit under `frontier-scout-receipts/` are part of the PR: either include that directory
in `allowed_file_globs`, or pass receipts from outside the PR with `--receipts`. The CLI
equivalent of the Action:

```bash
frontier-scout agent verify-pr --repo . --base "origin/main" \
  --receipts "frontier-scout-receipts/*.json" --json-out evidence.json
```

See [`examples/demo-walkthrough.md`](examples/demo-walkthrough.md) for a step-by-step
demo, and [`examples/sample-repo/`](examples/sample-repo/) for the end-to-end
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

### Optional: a decision model inside the hook

Off by default, and the compiled artifacts are identical whether or not you use it. A policy
may opt in to a System One decision model (TypeSafe's Jev) as a *second opinion* on Bash
calls, consulted by the hook after the static decision:

```json
{
  "decision_model": {
    "provider": "typesafe",
    "model": "jev-1.13.0",
    "key_env": "TYPESAFE_API_KEY",
    "timeout_seconds": 3.0,
    "relax_ask_to_allow_at": 0.95,
    "deny_at": 0.9,
    "ask_at": 0.5
  }
}
```

The hook asks four literal questions about the command (main effect; destructive; exposes
secrets; escalates privilege) and may only **tighten** an `allow` to `ask` when the model
rates the call possibly risky (`ask_at`) or an `allow`/`ask` to `deny` when it is confident
the call is risky (`deny_at`), or **relax** an `ask` to `allow` when it is confident the call
is read-only or build/test and not risky. A static `deny` is never relaxed. No key, a
timeout, a malformed or wrong-model answer, or a low-confidence answer leaves the static
decision in force, and the receipt says so (`decision_model.applied`: `tightened`,
`tightened-to-ask`, `relaxed`, `abstained` or `unavailable`). The key is read from the environment at hook time
and never written. Thresholds are yours to set from your own data. The default thresholds were
evaluated on the maintainer-labelled command corpus in
[`docs/evaluation/decision-model/`](docs/evaluation/decision-model/). Those results do not
establish general permission calibration or native-session enforcement.

## CLI

| Command | What it does |
|---|---|
| `agent verify-pr` | PR scope check: the real diff against the base commit's policy and lock; receipts are reported, never treated as approval (`--json`, `--json-out`) |
| `agent compile` | Compile the policy into Claude Code native controls + CI verifier |
| `agent scan` | Static repo agent-risk scan (secret-likely files by name only) |
| `agent policy init \| explain` | Generate / read a conservative policy |
| `agent check "<task>"` | Static pre-check of a proposed task (executes nothing) |
| `agent receipts list \| show` | Inspect local action records |
| `agent export agents-md \| pr-checklist` | Advisory policy snippets |
| `doctor` | Offline agent-readiness check |

## Safety model

- **Static + read-only.** The scan reads file *names*, never secret *contents*. The only
  subprocesses are read-only git calls (`rev-parse`, `diff`, `ls-tree`, `cat-file` in
  `verify-pr`; `rev-parse` for receipt metadata).
- **Keyless and offline by default.** The compiler, verifier, doctor and hooks make no
  network call unless a policy opts into the [decision model](#optional-a-decision-model-inside-the-hook),
  which is advisory and fail-closed: it can never relax a static `deny`, and any failure
  leaves the static decision in force.
- **Emit, don't enforce.** Frontier Scout writes native config; Claude Code's hook/permission
  system enforces locally and GitHub Actions enforces in CI.
- **Fail-closed where it can be.** In the hook, a missing or malformed policy denies by
  default and every dangerous capability escalates to approval. `verify-pr` never passes what
  it cannot establish (see [the verdicts](#repaired-verifier-220)). It does not authenticate
  approvals.
- **Redacted.** Every persisted/emitted string is scrubbed of secret-shaped tokens, including
  file paths in `verify-pr` findings and annotations; undecodable file-name bytes are emitted
  as `\xNN` markers.
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
records, the CI verifier (its scope-check repair shipped in 2.2.0; see above). P1 was **demand-gated** and the gates were not met at the
[day-90 evaluation](KILL_CRITERIA.md#day-90-evaluation-2026-09-30): platform-evidence
ingestion, Codex adapter, scanner findings as policy inputs stay unbuilt unless someone
with a real use case asks. See [ROADMAP.md](ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md), the design records in
[`docs/adrs/`](docs/adrs/), [SECURITY.md](SECURITY.md) (threat model, reporting) and the
[changelog](CHANGELOG.md). Tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`.
Lint/type: `make lint`, `make type`. Figures: `python3 docs/assets/src/make_figures.py --write`.

Maintained by Ajay Surya Senthilrajan, with AI pair-programming recorded in commit trailers. See the tests, design records and release evidence linked here.

## License

MIT — see [LICENSE](LICENSE).
