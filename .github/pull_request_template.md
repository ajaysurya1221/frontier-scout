## Summary

- 

## Verification

- [ ] `python -m compileall outputs tests frontier_scout`
- [ ] `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
- [ ] `make lint` · `make type`
- [ ] If the policy/compiler changed: re-ran `frontier-scout agent compile --repo . --out .` and committed any drift (the dogfood compile-golden test enforces this)
- [ ] Top-level docs updated if behavior/identity changed (README, AGENTS.md, CLAUDE.md, ROADMAP/CHANGELOG)
- [ ] No secrets, runtime ledgers, or noisy generated files in the diff

## Implementer provenance

Who/what produced this change — record what you know (`unknown` is fine):

- Implementer: `<Claude Code | Codex | human | other>`
- Model alias: `<e.g. claude-opus-4.x | unknown>`
- Effort setting: `<low | medium | high | unknown>`
- Permission-mode path: `<e.g. plan -> acceptEdits | bypassPermissions | unknown>`
- Provider path: `<Anthropic API | Claude Enterprise ZDR | Bedrock | Vertex | Foundry | other | unknown>`
- Non-essential traffic disabled: `<yes | no | unknown>`
- Feedback upload disabled: `<yes | no | unknown>`

(The last two are set by the env flags in CONTRIBUTING.md → "Implementation-session privacy".)

## Notes

Mention any compiler, policy-schema, hook, verifier, or security-behavior changes.
