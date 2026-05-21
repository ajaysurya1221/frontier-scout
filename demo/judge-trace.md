# Judge Trace — RLAIF decisions

_Generated for 2026-05-21 demo briefing. Shows the Opus 4.7 judge's per-draft decision (keep / veto / retier / promote) with rationale._

**Quality self-rating:** high
**Summary:** Tight upstream pass — vetoed two noise items, promoted one stack-direct trending repo. SOC2 calls are conservative and well-reasoned.

## ✅ Kept verdicts

### anthropics/skills → KEEP
**Verdict:** 🟢 ADOPT · ✅ SOC2-safe · severity 🔥 · readiness 5/5
**Judge reason:** Official Anthropic source, immediate stack-fit, low adoption cost, concrete next action with timebox.

### Gemini 3.5 Flash → KEEP
**Verdict:** 🟡 TRIAL · ⚠️ SOC2-conditional · severity ⭐ · readiness 5/5
**Judge reason:** Major lab release; existing Gemini integration means low integration overhead; SOC2 caveat is correctly conservative.

### obra/superpowers → PROMOTE (promoted from missed pool)
**Verdict:** 🟢 ADOPT · ⚠️ SOC2-conditional · severity ⭐ · readiness 4/5
**Judge reason:** Stack-direct trending repo missed by the verdict-gen pass; clear adoption path because we already use it.

### Forge (Guardrails for Agentic Tasks) → KEEP
**Verdict:** 🟡 TRIAL · ⚠️ SOC2-conditional · severity ⭐ · readiness 2/5
**Judge reason:** Promising reliability mechanism with concrete lab hypothesis; SOC2 conditional captures the solo-dev early-stage risk.

### Qwen3.6-35B-A3B → KEEP
**Verdict:** ⚪ ASSESS · ⚠️ SOC2-conditional · severity 📌 · readiness 4/5
**Judge reason:** Defensible 'assess' — provenance concern correctly captured; not urgent enough to promote.

### DeepSeek-V4-Pro → KEEP
**Verdict:** 🔴 HOLD · ❌ SOC2-blocked · severity 📌 · readiness 4/5
**Judge reason:** Correctly SOC2-blocked; verdict's restraint is appropriate.

## ❌ Vetoed drafts

### LlamaIndex v0.14.22 → VETOED (was draft `adopt`)
**Reason:** patch release of an already-adopted framework (55 sub-package lockfile bump). ADOPT bar requires a substantive API change or new capability; this is dependency hygiene.

### CISA AWS GovCloud Key Leak → VETOED (was draft `adopt`)
**Reason:** tool_name matches incident/breach pattern, not a tool/framework. The radar evaluates tools; security advisories belong in a different output channel.

---
_The judge layer turns the system from 'Sonnet's best guess' into 'Sonnet's best guess, audited by Opus.' Vetoes you see here are noise that would have shipped without the judge._
