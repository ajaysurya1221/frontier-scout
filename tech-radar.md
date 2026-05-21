# Frontier Scout — Tech Radar
_Seed file for public demos. Scheduled Scout runs will maintain this file._

Verdicts are tagged with **Category** and **SOC2 status**. SOC2-blocked tools
live in the dedicated section at the bottom so teams have a visible no-fly list.

> Legend: 🟢 ADOPT · 🟡 TRIAL · ⚪ ASSESS · 🔴 HOLD · ✅ SOC2-safe · ⚠️ SOC2-conditional · ❌ SOC2-blocked

---

## 🟢 Adopt
_Use now. Proven value._

### LangGraph — 🟢 ADOPT — 2026-05-19 — 🤖 Orchestration & Agents — ✅ SOC2-safe
**What**: Multi-agent orchestration with durable checkpoints and persistent state.
**Why it matters**: A strong default for production agent workflows that need graph control, resumability, and human review points.
**Adoption cost**: Already in many agent stacks; first prototype is usually hours, not weeks.
**Next action**: Track releases and test durable checkpointing on one workflow.

---

## 🟡 Trial
_30-minute lab experiment before committing._

### mem0 — 🟡 TRIAL — 2026-05-19 — 📊 Data Ecosystem — ⚠️ SOC2-conditional
**What**: Persistent semantic memory layer for agents.
**Why it matters**: Gives teams a concrete way to evaluate long-running memory without building a custom memory layer first.
**Adoption cost**: ~4 hours for a self-hosted lab on one workflow.
**Next action**: Run a lab and compare recall quality against the current session store.

---

## ⚪ Assess
_Interesting. Monitor for 3 months._

### deepagents — ⚪ ASSESS — 2026-05-19 — 🤖 Orchestration & Agents — ✅ SOC2-safe
**What**: LangGraph wrapper adding context management and human-in-loop primitives.
**Why it matters**: Promising for long-running sessions, but probably redundant for teams already comfortable with native LangGraph.
**Adoption cost**: ~1 week migration if context management becomes painful.
**Next action**: Monitor releases and revisit when long-session context becomes a real bottleneck.

---

## 🔴 Hold
_Evaluated. Skip. Re-evaluate in 6 months._

### Google ADK Python — 🔴 HOLD — 2026-05-19 — 🤖 Orchestration & Agents — ⚠️ SOC2-conditional
**What**: Gemini-native full agent framework requiring Vertex AI and a GCP-centric stack.
**Why it matters**: Useful for GCP-native teams, but a migration to a second cloud and framework is too costly for most existing LangGraph stacks.
**Adoption cost**: Weeks to months of migration plus vendor review.
**Next action**: Monitor for 6 months; re-evaluate only if the team chooses a GCP-native agent strategy.

---

## 🔴 Hold — SOC2 Blocked
_Do not adopt without legal/security review._

_(empty — record audit-blocking tools here so the team has a clear no-fly list)_

---
_Use `/radar <tool>` to query entries. Use the Slack `Lab` and `Evaluate` buttons to move from signal to evidence._
