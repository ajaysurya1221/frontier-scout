# Security Posture

Frontier Scout is a local-first CLI that **compiles** a typed repo policy into an AI coding
agent's native controls (Claude Code first) and **verifies** in CI that a PR stayed within
approved scope. It **emits** config and **verifies** evidence — Claude Code (hooks +
permissions) and GitHub Actions do the enforcing. Keyless and offline; the only runtime
dependency is `pydantic`. There is no hosted service, no backend, no LLM calls, and no
network egress.

## Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| Reading secret contents during a scan | The repo scan could read sensitive file bodies | The scan classifies risk surfaces by **file name/path only** — it never opens or reads file contents. |
| Arbitrary command execution | A subprocess could run untrusted input | The only subprocess is a **read-only `git diff` / `git rev-parse`** with a fixed argv (no shell). No agent task, MCP server, or package is ever executed. |
| Config mistaken for a guarantee | A team assumes the compiled hooks/settings fully prevent unsafe actions | Local hooks are **not a complete enforcement boundary** (a model can route around one tool). They are deliberately paired with the **fail-closed CI diff verifier**. Output is documented as **control evidence, not a guarantee**. |
| Policy drift / weakened guardrails | The policy is edited out-of-band, or an agent weakens its own policy | `policy.lock.json` pins the policy sha256; `verify-pr` rejects receipts whose hash drifts from the lock, and flags protected-path changes (the policy/lock/hooks can be self-protected). |
| Spoofed or missing evidence | A PR with no receipts, or receipts from a different policy | `verify-pr` is **fail-closed**: a non-empty protected diff with no covering receipt fails; stale-hash receipts fail; a `deny`-decision file that still changed fails. (P1: optional export/integration with existing receipt/provenance systems.) |
| Off-policy MCP use | An agent calls an MCP server outside the sanctioned set | The compiled managed allow/deny fragment + the hook **deny-by-default** any MCP server not on `mcp_server_allowlist`. |
| Secret leakage into artifacts | A token rides in a receipt, snippet, or emitted config | Every persisted/emitted string runs through `scrub_secrets` (Anthropic/OpenAI/GitHub/Slack/AWS/npm/bearer shapes). |

## Secrets

Frontier Scout itself needs **no API keys or tokens** — compile and verify are deterministic
and offline. In CI, the verify workflow uses the standard `GITHUB_TOKEN` only for PR
annotations. If a secret is ever pasted into chat, logs, an issue, or a public branch,
rotate it immediately.

## Local data

Frontier Scout writes only **local action receipts** to `<repo>/.frontier-scout/receipts/`
(gitignored) — redacted JSON records of what the agent was allowed to do. PR-visible
evidence is committed under `frontier-scout-receipts/`. There is no database, cost ledger,
or lab transcript.

These are **redacted local control evidence for PR scope verification, not a signed portable
receipt protocol.** Frontier Scout does not provide key custody, signing daemons, receipt
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
