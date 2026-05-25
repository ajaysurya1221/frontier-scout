---
title: Cache Rollout Config Fixture
service: cache-service
visibility: team
---

# Cache Rollout Config Fixture

service: cache-service

Current rollout concurrency is 25 percent with speculative cache warming enabled.
During incidents, the safe proposed change is concurrency 5 percent and cache warming disabled until redis-cluster saturation clears.

