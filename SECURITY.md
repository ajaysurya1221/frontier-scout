# Security Posture

Frontier Scout is a local-first CLI that **compiles** a typed repo policy into an AI coding
agent's native controls (Claude Code first) and **checks** in CI that a PR's diff stays
inside the policy scope declared at the base commit. It **emits** config and **checks**
evidence. Claude Code (hooks and permissions) and GitHub Actions do the enforcing. It is a
research preview. It is keyless and offline by default, and its only runtime dependency is
`pydantic`. There is no hosted service and no backend. The hook makes a network call only if
a policy opts into the `decision_model` section.

## Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| Reading secret contents during a scan | The repo scan could read sensitive file bodies | The scan classifies risk surfaces by **file name/path only** — it never opens or reads file contents. |
| Arbitrary command execution | A subprocess could run untrusted input | The only subprocesses are **read-only git calls** (`rev-parse`, `diff`, `ls-tree`, `cat-file`) with a fixed argv and no shell. An option-shaped `--base` (for example `--output=…`) is rejected before git sees it. No agent task, MCP server, or package is ever executed. |
| Config mistaken for a guarantee | A team assumes the compiled hooks/settings fully prevent unsafe actions | Local hooks are **not a complete enforcement boundary** (a model can route around one tool). They are deliberately paired with the **CI diff scope check**. Output is documented as **control evidence, not a guarantee**. |
| Policy drift / weakened guardrails | The policy is edited out-of-band, or an agent widens its own policy in the PR | `verify-pr` reads the policy and `policy.lock.json` from the **base commit**, so a PR cannot widen its own scope. A PR that changes either file is itself a protected change. A missing, malformed or drifted policy identity fails. |
| Out-of-scope or disguised changes | A PR touches paths outside `allowed_file_globs`, renames a protected file out of its directory, or hides a path behind quoting | Every changed path from `git diff --name-status -z -M`, including both rename ends, deletions, mode-only and binary changes, and names with spaces, tabs, quotes, newlines or non-ASCII characters, is checked. Out-of-scope paths fail. A missing or failed diff is UNVERIFIED, never PASS. |
| Spoofed or missing evidence | A PR with no receipts, receipts claiming approval, receipts committed in the PR, or receipts from a different policy | Receipts are unsigned JSON from the agent's machine and **never count as approval**. A protected change fails with no receipt and is UNVERIFIED with one. Receipts committed in the PR are flagged. Malformed, unbound (no policy hash) and stale receipts fail. A file that changed despite a `deny` record fails. **Not mitigated:** authenticating who approved a protected change. That requires an approval record outside the agent's control and is deferred. |
| PR edits the check itself | On `pull_request`, GitHub runs the workflow file from the PR | **Not mitigated by the verifier.** `.github/workflows/**` is protected by default, but a PR can remove or alter the verify step. If the check must gate merges, run it from a workflow the PR cannot edit (for example, a required workflow in an organization ruleset, pinned to a trusted ref). The Action installs its own pinned ref and the generated workflow pins the PyPI release, but a PR that edits the workflow can change either. |
| PR code executed by the Action | A PR-root `pip.py`, `json.py` or `frontier_scout/` shadows the installer, the verifier or the output helpers when Python runs from the checkout | Every Action step runs from `$RUNNER_TEMP`, and every Python call is `python -I` (no current or script directory on `sys.path`, no user site, `PYTHON*` variables ignored); the checkout reaches the verifier only as an absolute `--repo` path. `tests/test_action_isolation.py` runs the steps against shadow modules and asserts none is imported. **v2.1.0 and earlier are affected:** their Action runs Python from the checkout. The generated workflow uses the `pip` and `frontier-scout` console scripts, which do not import from the working directory, but it does not use `-I`. |
| Off-policy MCP use | An agent calls an MCP server outside the sanctioned set | The compiled managed allow/deny fragment + the hook **deny-by-default** any MCP server not on `mcp_server_allowlist`. |
| Secret leakage into artifacts | A token rides in a receipt, snippet, emitted config, or a file name in `verify-pr` output | Every persisted/emitted string runs through `scrub_secrets` (Anthropic/OpenAI/GitHub/Slack/AWS/npm/bearer shapes), including finding paths and annotation `file=` properties. |

## Secrets

Frontier Scout itself needs **no API keys or tokens** — compile and verify are deterministic
and offline. In CI, the verify workflow uses the standard `GITHUB_TOKEN` only for PR
annotations. If a secret is ever pasted into chat, logs, an issue, or a public branch,
rotate it immediately.

## Local data

Frontier Scout writes only **local action receipts** to `<repo>/.frontier-scout/receipts/`
(gitignored): redacted JSON records of what the hook decided and observed. Receipts committed
under `frontier-scout-receipts/` are PR content. They must be inside `allowed_file_globs`,
they are flagged as PR-supplied, and like every receipt they never authorise a change. There
is no database, cost ledger, or lab transcript.

These are **redacted, unsigned observations that the PR scope check reports. They are not
approvals and not a signed portable receipt protocol.** Frontier Scout does not provide key custody, signing daemons, receipt
SDKs, MCP receipt proxies, dashboards, transparency logs, or ledger infrastructure; for
portable, signed evidence it should integrate with existing receipt/provenance systems
rather than build its own.

## Reporting a security issue

Do not file public issues for vulnerabilities.

Preferred channel: use GitHub private vulnerability reporting for this repository. If private
reporting is unavailable, open a minimal public issue that asks for a private contact path
without disclosing the vulnerability details.

Include reproduction steps, affected version/commit, expected impact, and any relevant local
configuration. Redact API keys, tokens, private repository names, and local filesystem paths.
