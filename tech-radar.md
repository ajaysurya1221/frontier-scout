# Frontier Scout — Tech Radar
_Maintained by ai-analyst skill. Last restructured: 2026-05-20_

Verdicts are tagged with **Category** and **SOC2 status**. SOC2-blocked tools live in the dedicated section at the bottom — adopting any of those would jeopardize the security audit.

> Legend: 🟢 ADOPT · 🟡 TRIAL · ⚪ ASSESS · 🔴 HOLD · ✅ SOC2-safe · ⚠️ SOC2-conditional · ❌ SOC2-blocked

---

## 🟢 Adopt
_Use now. Proven value._

### Claude Code + superpowers — 🟢 ADOPT — 2026-05-17 — 🛠️ Tools & Frameworks — ✅ SOC2-safe
**What**: Anthropic's official CLI + the superpowers plugin pack with the brainstorming/debugging skill suite.
**Why it matters**: Already the core dev loop for genai-core. Anthropic holds SOC2 Type II. The agentskills.io plugin ecosystem is the right bet for shared engineering practice.
**Adoption cost**: Already done.
**Next action**: Stay current with plugin releases.

### LangGraph — 🟢 ADOPT — 2026-05-19 — 🤖 Orchestration & Agents — ✅ SOC2-safe
**What**: Multi-agent orchestration with durable checkpoints and persistent state.
**Why it matters**: Backbone of genai-core's agentic workflows. LangChain ecosystem aligned with our LangSmith decision.
**Adoption cost**: Already done.
**Next action**: Track 0.6.x release notes; trial durable checkpoints to replace Redis session hack.

### LangSmith — 🟢 ADOPT — 2026-05 — 🤖 Orchestration & Agents — ✅ SOC2-safe
**What**: Production observability and tracing for LangChain/LangGraph.
**Why it matters**: Chosen over LangFuse via AI-1037 (LangFuse had ECS nesting bug). LangChain is SOC2 Type II.
**Adoption cost**: Already done.
**Next action**: Nothing.

### agentskills.io format — 🟢 ADOPT — 2026-05-19 — 🛠️ Tools & Frameworks — ✅ SOC2-safe
**What**: Open SKILL.md standard. Works across 35+ clients (Claude Code, Codex, Cursor, Copilot).
**Why it matters**: Future-proofs our skill library against any single client lock-in.
**Adoption cost**: Already done — all radar skills are agentskills.io-shaped.
**Next action**: Nothing.

### ccusage — 🟢 ADOPT — 2026-05-19 — 🛠️ Tools & Frameworks — ✅ SOC2-safe
**What**: `npx ccusage@latest` — zero-install local token cost analysis.
**Why it matters**: Per-engineer visibility into Claude Code spend with no install footprint.
**Adoption cost**: Zero.
**Next action**: Recommend to the team.

---

## 🟡 Trial
_30-minute lab experiment before committing._

### mem0 — 🟡 TRIAL — 2026-05-19 — 📊 Data Ecosystem — ⚠️ SOC2-conditional
**What**: Persistent semantic memory layer for agents — `pip install mem0ai`. Now powering the Radar's own semantic memory.
**Why it matters**: Cleaner upgrade path from our Redis key-value session store for genai-core. Already validated by being our radar's own memory layer (self-hosted, SOC2-safe in that config).
**Adoption cost**: ~4 hrs to swap one workflow. Self-host required for SOC2 compliance.
**Next action**: `lab mem0` — swap session store on one genai-core flow and measure recall quality.

---

## ⚪ Assess
_Interesting. Monitor for 3 months._

### Hermes Agent — ⚪ ASSESS — 2026-05-19 — 🤖 Orchestration & Agents — ⚠️ SOC2-conditional
**What**: Nous Research's 140k-star self-evolving multi-platform agent (Telegram/Discord/Slack).
**Why it matters**: Self-evolution pattern is interesting but doesn't map to FastAPI/LangGraph today.
**Adoption cost**: Migration would be months. Not appropriate.
**Next action**: Watch the self-evolution research thread. Revisit Q3.

### deepagents — ⚪ ASSESS — 2026-05-19 — 🤖 Orchestration & Agents — ✅ SOC2-safe
**What**: LangGraph wrapper adding context management + human-in-loop primitives.
**Why it matters**: Mostly redundant given our existing LangGraph setup. Revisit only if long-session context becomes a real pain point.
**Adoption cost**: ~1 week migration if context becomes painful.
**Next action**: Monitor for 3 months.

---

## 🔴 Hold
_Evaluated. Skip. Re-evaluate in 6 months._

### Google ADK Python — 🔴 HOLD — 2026-05-19 — 🤖 Orchestration & Agents — ⚠️ SOC2-conditional
**What**: Gemini-native full agent framework requiring Vertex AI and a GCP-centric stack.
**Why it matters**: Would force a complete LangGraph rewrite and add GCP as a second cloud vendor — doubles SOC2 scope.
**Adoption cost**: Months of rewrite + dual-cloud audit expansion.
**Next action**: Monitor for 6 months. Re-evaluate only if Anthropic announces parity issues.

---

## 🔴 Hold — SOC2 Blocked
_Would jeopardize the target SOC2 audit. DO NOT adopt in production._

_(empty — record any audit-blocking tools here so the team has a clear "no-fly list")_

---
_Use `evaluate <tool>` to add entries. Use `lab <tool>` to move Trial → Adopt. Use `recall <topic>` to query past verdicts via Mem0._
