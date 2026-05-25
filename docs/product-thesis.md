# Product Thesis: Incident Change Scout

## Painful Problem

Enterprise incidents are evidence-heavy and permission-sensitive. Engineers
need to know which services are related, which runbooks apply, who owns the
system, what change is safe, and whether the proposed action is allowed.
Generic agents are too unconstrained for this job.

## User

The user is a senior engineer, on-call lead, or platform engineer who needs a
locally reproducible incident assistant with citations, policy checks, and
auditability.

## Demo Path

`make demo` runs a complete local incident analysis over the seed corpus:
ticket → authorized retrieval → graph-aware context packet → plan → approval
interrupt → cited answer → trace → audit log → eval score.

## Why Now

MCP tools, agent runtimes, and model gateways have made action-taking AI
systems practical, but enterprises still need policy, provenance, approvals,
and measurable quality before they trust them.

## What Is Novel

Incident Change Scout is not another agent framework. It is a control plane
vertical slice where every answer carries evidence and every risky action is
bound by authorization and approval.

## Proof

The proof is operational: local demo under five minutes, deterministic eval,
authz tests in retrieval and action paths, audit and trace artifacts for every
meaningful action, and prompt metadata linked to eval IDs.

