# Blockers

No functional release blockers remain for the local v0.2.0 release slice.

The local path (`make demo`) and Docker compose path have both been validated:
the incident demo runs without model API keys, Qdrant starts, the OpenTelemetry
collector starts, and the app container exits successfully after writing the
answer, trace, audit log, and eval result.

Optional production integrations still need operator configuration:

- PyPI trusted publishing: the GitHub release workflow expects an environment
  named `pypi`, but GitHub returned `404` for that environment during the
  release audit. Configure the GitHub environment and PyPI trusted publisher
  before pushing the `v0.2.0` tag.
- live OpenAI/Anthropic model adapters,
- remote MCP servers,
- production OpenFGA/SpiceDB,
- production OTel collector,
- Qdrant-backed vector retrieval beyond the deterministic local fallback.
