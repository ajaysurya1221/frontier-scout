# AI Telemetry — Weekly Briefing · 2026-05-21
> Scanned **377** items · **350** considered after dedup + Mem0 prior-filter · **6** verdicts after RLAIF judge pass. Run cost **$0.3100** (cached). Judge confidence: **high**.

> _Tight upstream pass — vetoed two noise items, promoted one stack-direct trending repo. SOC2 calls are conservative and well-reasoned._

### 🔥 [anthropics/skills](https://github.com/anthropics/skills) — 🟢 ADOPT — 2026-05-21 — 🛠️ Tools & Frameworks — ✅ SOC2-safe
**What**: Anthropic's official public repository of Agent Skills — reusable, composable capability modules for Claude-based agents.
**Why it matters**: Skills primitives accelerate building agentic capabilities (retrieval, structured extraction, tool-use patterns) without reinventing plumbing, and carry implicit compatibility guarantees with Claude model updates.
**Why this week**: Public release this week with broad surge in adoption across Claude Code, Codex and Cursor integrations.
**Adoption cost**: ~2 hrs to audit + prototype one skill in an existing agent · low risk
**Next action**: Lab — clone, identify one skill applicable to document extraction, integrate into one LangGraph node, demo to the team within 1 sprint.
**Readiness**: `▰▰▰▰▰` 5/5

### ⭐ [Gemini 3.5 Flash](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/) — 🟡 TRIAL — 2026-05-21 — 🧠 Frontier Models — ⚠️ SOC2-conditional
**What**: Google's new GA fast/cheap frontier model, deployed across Search and Gemini app at scale.
**Why it matters**: Flash-tier pricing makes it a credible candidate for high-volume document classification where Sonnet cost dominates. GA-from-day-one signals production readiness; SOC2 conditional pending Vertex AI data residency confirmation.
**Why this week**: Skipped preview and jumped straight to GA — Google is signaling production-confidence on the Flash tier.
**Adoption cost**: ~3 hrs benchmark vs Sonnet on 50 classification samples · medium risk (verify Vertex training opt-out)
**Next action**: Evaluate — run head-to-head benchmark on document classification; check Vertex AI data-processing addendum for training opt-out before any prod data path.
**Readiness**: `▰▰▰▰▰` 5/5

### ⭐ [obra/superpowers](https://github.com/obra/superpowers) — 🟢 ADOPT — 2026-05-21 — 🛠️ Tools & Frameworks — ⚠️ SOC2-conditional
**What**: Agentic skills framework + software development methodology already on our dev stack.
**Why it matters**: Stack-direct hit. 10,577 stars this week signals a major version or surge — check if our pinned version is current and whether new skills are relevant to ongoing work.
**Why this week**: Trending hard on GitHub this week (+10.5k stars in 7 days) — strong signal something changed.
**Adoption cost**: Already on the dev stack · upgrade audit is ~1 hr
**Next action**: Audit current pin against latest release; review changelog for breaking changes; bump version if compatible.
**Readiness**: `▰▰▰▰▱` 4/5

### ⭐ [Forge (Guardrails for Agentic Tasks)](https://github.com/antoinezambelli/forge) — 🟡 TRIAL — 2026-05-21 — 🤖 Orchestration & Agents — ⚠️ SOC2-conditional
**What**: Open-source guardrail framework that lifts an 8B-model task-completion rate from 53% to 99% on agentic benchmarks via proposer + verifier loops.
**Why it matters**: Reliability claim is compelling for domains where a hallucinated extraction or citation is a trust-killer. Complements deepeval already in the stack.
**Adoption cost**: ~4-6 hrs to wrap one LangGraph node · medium risk (early-stage project, API may shift)
**Next action**: Lab — apply Forge guardrails to one agent node; compare output validity rate against baseline using deepeval; timebox to 4 hrs.
**Readiness**: `▰▰▱▱▱` 2/5

### 📌 [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) — ⚪ ASSESS — 2026-05-21 — 🧠 Frontier Models — ⚠️ SOC2-conditional
**What**: Alibaba open-weight multimodal MoE (35B total / 3B active), Apache-2.0, 5.8M downloads on HuggingFace.
**Why it matters**: Apache-2.0 + MoE efficiency makes this interesting for self-hosted inference. 3B active params runs on smaller GPU instances. Alibaba provenance needs legal sign-off before any prod path.
**Adoption cost**: 1-2 days to stand up on SageMaker for benchmarking · medium risk (legal review required)
**Next action**: Monitor 3 months — watch for independent evals on document-heavy tasks; revisit when self-host fallback is a real need.
**Readiness**: `▰▰▰▰▱` 4/5

### 📌 [DeepSeek-V4-Pro](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro) — 🔴 HOLD — 2026-05-21 — 🧠 Frontier Models — ❌ SOC2-blocked
**What**: DeepSeek open-weight frontier model, MIT license, 3.8M downloads on HuggingFace.
**Why it matters**: Chinese AI lab with documented data-residency ambiguity and ongoing US regulatory scrutiny. Prior versions had telemetry questions never fully resolved.
**Adoption cost**: N/A — blocked on SOC2 and compliance grounds regardless of self-hosting posture.
**Next action**: Hold indefinitely. Revisit only if legal counsel explicitly clears it.
**Readiness**: `▰▰▰▰▱` 4/5

---
*Dig deeper: `evaluate <tool>` · Build skill: `lab <tool>` · Recall past verdicts: `recall <topic>`*
