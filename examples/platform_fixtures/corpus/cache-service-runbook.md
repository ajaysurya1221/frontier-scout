---
title: Cache Service Incident Runbook
service: cache-service
visibility: team
---

# Cache Service Incident Runbook

service: cache-service
depends_on: redis-cluster
calls: checkout-api
owned_by: alice
alerts_to: oncall-cache

If checkout latency rises after a cache-service rollout, first check redis-cluster saturation and cache hit rate.
Safe mitigation is to reduce rollout concurrency and disable speculative cache warming.
Any production config write requires cache-service owner approval.

