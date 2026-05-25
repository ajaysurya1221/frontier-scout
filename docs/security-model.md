# Security Model

## OWASP Agentic Mapping

- **ASI03 policy bypass:** ReBAC checks run in retrieval and action paths.
  Tests: `tests/test_platform_authz.py`, `tests/test_platform_retrieval.py`.
- **ASI05 unexpected code execution:** high-risk tools require explicit
  approval and are disabled by default. Tests:
  `tests/test_platform_orchestration_tools.py`.
- **ASI06 memory/context poisoning:** context compiler binds citations and uses
  stable policy/schema prefixes. Tests: `tests/test_platform_context_gateway.py`.
- **ASI08 cascading failures:** DCG runtime has bounded steps/retries and
  interrupts. Tests: `tests/test_platform_orchestration_tools.py`.
- **ASI09 trust exploitation:** output includes citations, trace, audit log,
  and approval state. Tests: `tests/test_incident_change_scout.py`.

## Defaults

No external writes, authenticated browser actions, shell actions, or
non-allowlisted MCP calls execute in the local demo.

