# Demo: fail-closed scope verification in 90 seconds

What this shows: an out-of-scope agent change **fails closed** in the verifier with a
GitHub-ready annotation and a machine-readable evidence file — then passes once a covering
action record exists. Everything below uses shipped capability only.

> In a real setup the compiled Claude Code hook writes the action records during the agent
> session; here we hand-write one to show the mechanism without running an agent.

## 1. A repo with a policy

```bash
pip install frontier-scout
mkdir scope-demo && cd scope-demo

cat > frontier-scout.policy.json <<'EOF'
{
  "policy_version": 1,
  "allowed_file_globs": ["src/**", "tests/**"],
  "protected_file_globs": ["**/migrations/**", ".github/workflows/**"]
}
EOF

frontier-scout agent compile --repo .   # native controls + policy.lock.json
git init -q && git add -A && git commit -qm "base (compiled controls)"
BASE=$(git rev-parse HEAD)
```

## 2. The agent makes an out-of-scope change

```bash
mkdir -p app/migrations
echo "# schema change" > app/migrations/0001_init.py
git add -A && git commit -qm "agent: add migration"
```

## 3. Verify — fail-closed

```bash
frontier-scout agent verify-pr --repo . --base "$BASE" --json-out evidence.json
echo "exit: $?"
```

Output:

```
::error file=app/migrations/0001_init.py::app/migrations/0001_init.py: protected path changed without an action receipt (fail-closed).
FAIL: 1 changed file(s), 0 receipt(s), 1 violation(s), 0 warning(s).
  violation: app/migrations/0001_init.py: protected path changed without an action receipt (fail-closed).
exit: 1
```

`evidence.json` carries the same verdict, machine-readable (`"ok": false`,
`"advisory": false` — advisory runs are self-describing so exported evidence can't
masquerade as an enforcing pass).

## 4. Add the covering action record — pass

```bash
PH=$(python3 -c "import json; print(json.load(open('policy.lock.json'))['policy_sha256'])")
mkdir -p frontier-scout-receipts
cat > frontier-scout-receipts/r1.json <<EOF
{
  "receipt_id": "r1", "kind": "agent-action", "policy_hash": "$PH",
  "tool_name": "Edit", "decision": "ask", "verdict": "needs_approval",
  "files_considered": ["app/migrations/0001_init.py"]
}
EOF

frontier-scout agent verify-pr --repo . --base "$BASE" \
  --receipts "frontier-scout-receipts/*.json" --json-out evidence.json
echo "exit: $?"
```

```
PASS: 1 changed file(s), 1 receipt(s), 0 violation(s), 0 warning(s).
exit: 0
```

Change one byte of the policy without recompiling, or point `--base` at an unfetched ref,
and the verdict is **drift** / **UNVERIFIED** respectively — never a silent pass.

## 5. The same thing in CI, signed

The [README quickstart](../README.md#quickstart-the-github-action) wires this as a GitHub
Action; with `attest: "true"` the evidence JSON is signed via GitHub attestations and
anyone can check it:

```bash
gh attestation verify evidence.json --owner <org-or-user> \
  --predicate-type https://github.com/ajaysurya1221/frontier-scout/predicate/verify-pr/v1
```

What this demo is **not**: CI-gaming detection (deleted tests, `|| true`), semantic
intent verification, or a security boundary. Scope + evidence, fail-closed — that's the
product.
