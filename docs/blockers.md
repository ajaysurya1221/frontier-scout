# Blockers

No functional release blockers remain for the local v0.1.0 release slice.

The local path (`make demo`) and Docker compose path have both been validated:
the incident demo runs without model API keys, Qdrant starts, the OpenTelemetry
collector starts, and the app container exits successfully after writing the
answer, trace, audit log, and eval result.

Optional production integrations still need operator configuration:

- live OpenAI/Anthropic model adapters,
- remote MCP servers,
- production OpenFGA/SpiceDB,
- production OTel collector,
- Qdrant-backed vector retrieval beyond the deterministic local fallback.
