# Sample repo — Frontier Scout compile → receipts → verify-pr

A minimal repo that demonstrates the Frontier Scout spine: compile a repo policy
into **Claude Code native controls**, let the agent run under those controls
(emitting **receipts**), then **check the PR diff** in CI against the scope the base
commit's policy declares. Frontier Scout *emits* config and *checks* evidence; Claude Code and
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

## 3. Open a PR — CI checks the diff against the base policy

Receipts are optional supporting observations. If you commit them to
`frontier-scout-receipts/`, they are part of the PR and must be inside
`allowed_file_globs`. You can also pass them from outside the PR with `--receipts`. The
generated workflow runs:

```bash
frontier-scout agent verify-pr --repo . --base "origin/main" \
  --receipts "frontier-scout-receipts/*.json"
```

The policy and lock are read from the base commit. **FAIL** covers a path outside
`allowed_file_globs`, a protected-path change with no receipt, a missing, malformed or
drifted policy or lock, a malformed, unbound or stale receipt, and a change made despite a
`deny` decision. **UNVERIFIED**, never a pass, covers a protected-path change backed only by
receipts, since receipts are unsigned and cannot authenticate an approval, and a diff that
could not be collected. Output is **control evidence, not a guarantee** that no unsafe action
occurred.

Use `--advisory` to downgrade violations to warnings while a repo is still being
onboarded. The verdict is still reported, marked as advisory.
