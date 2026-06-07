# Sample repo — Frontier Scout compile → receipts → verify-pr

A minimal repo that demonstrates the Frontier Scout spine: compile a repo policy
into **Claude Code native controls**, let the agent run under those controls
(emitting **receipts**), then **verify the PR** in CI stayed within the approved
scope. Frontier Scout *emits* config and *verifies* evidence — Claude Code and
GitHub Actions do the enforcing. Nothing here executes an agent or an MCP server
on your behalf.

## 1. Compile the policy into native controls

```bash
cd examples/sample-repo
frontier-scout agent compile --target claude --repo . --out .
```

This writes (from [`frontier-scout.policy.json`](frontier-scout.policy.json)):

| Artifact | Purpose |
|---|---|
| `.claude/settings.json` | `permissions` (allow/deny/ask) + hook wiring |
| `.claude/hooks/pre_tool_use.py` · `post_tool_use.py` | decide allow/deny/ask, write receipts |
| `.claude/hooks/_fs_guard.py` | self-contained (stdlib-only) decision + receipt logic |
| `policy.lock.json` | sha256 binding receipts to this exact policy |
| `managed-settings.json` | admin/MDM MCP allow/deny fragment |
| `.github/workflows/frontier-scout-verify.yml` | the PR verifier check |

> Re-run `agent compile` whenever you edit the policy — receipts written under a
> stale policy are rejected by the verifier. Claude Code reads settings at launch,
> so restart the session after recompiling.

## 2. Run Claude Code normally

The `PreToolUse` hook decides **allow / deny / ask** for each real tool call and
writes a redacted receipt to `.frontier-scout/receipts/`. Example outcomes under
the sample policy:

- `pytest -q` → **allow** (allowlisted command)
- editing `src/calculator.py` → **allow** (allowed path)
- editing `app/migrations/0001.py` → **ask** (protected path)
- `rm -rf …` → **deny** (blocked command)
- an MCP server not named `github` → **deny** (deny-by-default)

## 3. Open a PR — CI verifies the evidence

Commit the receipts you want verified to `frontier-scout-receipts/` (or upload
them as a CI artifact). The generated workflow runs:

```bash
frontier-scout agent verify-pr --repo . --base "origin/main" \
  --receipts "frontier-scout-receipts/*.json"
```

It **fails closed**: a protected-path change with no covering receipt, a receipt
whose `policy_hash` drifted from the lock, or a change that happened despite a
`deny` decision all block the PR. Output is **control evidence, not a guarantee**
that no unsafe action occurred.

Use `--advisory` to downgrade violations to warnings while a repo is still being
onboarded.
