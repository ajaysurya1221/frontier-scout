# Frontier Scout — README Design Handoff Kit

Everything needed to design the perfect README — identity, claim-honesty guardrails, rendering
constraints, the visual system, an asset inventory, a section-by-section layout, a copy bank, and an
acceptance checklist. Hand this (plus the two reference SVGs) to a designer or to Claude Design.

> **Non-negotiable:** this is a **research preview**, not a launched product. Every design choice must
> stay inside the **Claim-honesty guardrails** in §2. Beautiful + dishonest = rejected.

Reference assets already produced (use as the style anchor):
`docs/assets/hero-banner.svg` (1280×470) · `docs/assets/frontier-scout-social-preview.svg` (1280×640) ·
the CLI gold-path in `docs/examples/sanctioned-packs/`.

---

## 1. The one identity (positioning)

**Frontier Scout is a research-preview tool that turns "which MCP servers are safe for our team's Claude
Code?" into a one-step decision.** It ranks approved MCP servers to *your* repo, gives each a **static**
capability + policy safety read, and exports the approved set as a **Claude Code managed-config fragment**
an admin deploys. It is a *curation + translation overlay* into a control plane you already own — not a
runtime, not an enforcer, not a registry.

One-liner: **Repo-rank approved MCP servers → a static safety map → a Claude Code managed-config fragment.**

The old "AI adoption radar / Mission Control TUI" is the **engine underneath**, not the headline.

---

## 2. Claim-honesty guardrails (LOAD-BEARING — read before any pixel)

**MUST say / imply (true today):**
- Research preview — technically coherent, **not market-validated** (no PMF / adoption claim).
- **Claude Code first.** Managed-config export is the one supported target today.
- **Static analysis only** — *no MCP server is executed* in the sanctioned-pack flow.
- **Emits** config fragments for admin/developer review; an admin deploys them. **Does not enforce** runtime policy.
- Keyless, offline, local-first, no telemetry, MIT.
- Copilot / Cursor / Docker / GitHub allow-list = **roadmap**, not built.

**MUST NOT say / imply (will get the project caught overclaiming):**
- ❌ "AI-tool radar" as the main product · ❌ receipts as the headline · ❌ a CI guard / GitHub Action wedge.
- ❌ runtime enforcement / governance / "secures" / "blocks installs" / "control plane" *that FS owns*.
- ❌ executing / running / **sandboxing** / "trialing" MCP servers in the pack flow.
- ❌ native Copilot / Cursor / Docker support **today**.
- ❌ "registry" / "verified catalog" (FS reads registries; it isn't one).
- ❌ market validation / PMF / demand proof / "design partners validated it" / star-count bragging.

**Banned words in hero/social art:** `radar`, `receipt`, `sandbox`, `enforce`, `runtime policy`,
`cross-client`, `copilot`, `cursor`, `docker`, `market validated`, `PMF`. (Verify with a grep — see §9.)

---

## 3. Hard rendering constraints (GitHub)

GitHub renders README HTML through a sanitizer and proxies images through `camo.githubusercontent.com`.

| Survives | Stripped |
|---|---|
| `<img>`/`<picture>` referencing **`.svg` files**; `<table>`, `<details>`, `<kbd>`, `<sub>`, `align=`, anchor links, shields.io badges | `style=`, `<style>`, `class`/`id`, `<script>`, inline `<svg>`, **`<foreignObject>`**, JS, `@import`, external fonts/CSS |
| **Inside an SVG file:** native elements (`text/rect/path/circle/linearGradient/radialGradient/pattern/filter`) **and SMIL `<animate>`/`<animateTransform>`** | Inside an SVG: `<style>`, CSS `@keyframes`, `<foreignObject>`, `:hover`, web fonts |

**Implication:** all visual richness lives in **baked `.svg` files** referenced via `<img>`/`<picture>`.

### The one big design decision — static vs. animated
The repo's current convention (see the README HTML comment) is **static, system-mono, no animation,
light/dark-safe**. That is a *legitimate, on-brand* choice for a security/research tool (calm, credible).
**SMIL animation would survive GitHub** if you want more punch (subtle gradient shimmer, a flowing arrow on
the RANK→CHECK→EXPORT path, a pulsing "high-risk" dot). Pick one lane and apply it consistently:

- **Lane A — Static (current):** one SVG per component on a dark bg, renders identically light/dark. Lowest
  risk, most credible. *The two reference assets are Lane A.*
- **Lane B — Subtle SMIL motion:** same components + 1–2 restrained animations (3–6s cycles). More alive;
  still 100% GitHub-safe. If you choose this, animate **one** thing per component, never the whole canvas.

If you go Lane B and also want true light/light backgrounds, ship **dark + light SVG variants** per
component and wire them with `<picture>` (§7). Lane A on a dark bg needs no light variant.

---

## 4. Visual system

**Palette (use these hex exactly — they're baked into the reference SVGs):**

| Token | Hex | Use |
|---|---|---|
| bg | `#05080b` | canvas background (near-black) |
| mint | `#24d6a8` | primary accent — SCOUT wordmark, arrows, "go", links |
| ice | `#d9f7ff` | FRONTIER wordmark, headline text |
| slate | `#a9bccd` | body / value-prop text |
| line | `#1a2c41` | borders, dividers, card strokes |
| muted | `#46596b` | chips, captions, footnotes |
| risk-red | `#ff6b6b` | **only** the "high-risk gated" accent dot / a config window button |

**Typography:** the README's anchor is **system-mono** — `ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo,
Consolas, 'DejaVu Sans Mono', monospace` (escape apostrophes in SVG: `&#39;`). It reads "developer tool,
honest, terminal." Keep wordmarks heavy (font-weight 700, large), body lighter. *(If you ever want a display
face, bake the text as `<path>` outlines so it survives without a web font — but mono is the brand.)*

**Motif language (reuse across components):**
- The product is a **left→right flow: `RANK → CHECK → EXPORT`**. Use mint connector arrows.
- `RANK` = a small repo-ranked list card (server name + `fit`/`risk` tags + "your repo · tree-sitter").
- `CHECK` = a **static safety** check/shield with a green ✓, the words **"no server run"**, and a small
  red **"high-risk gated"** dot.
- `EXPORT` = a `{ }` config card (mac-window dots) showing `"allowedMcpServers": …` / `"deniedMcpServers": [ ]`
  with **"managed · admin deploys"**.
- **No radar concentric-circles motif.** That was the old identity.

**Tone:** calm, precise, credible, a little terminal. Whitespace is a feature. Avoid hype words and emoji in
headings (keep heading anchors stable).

---

## 5. Asset inventory & status (`docs/assets/`)

| File | Shows now | Status | Action |
|---|---|---|---|
| `hero-banner.svg` (1280×470) | **NEW** sanctioned-packs flow | ✅ honest (reference) | keep; it's the README `<img>` at the top |
| `frontier-scout-social-preview.svg` (1280×640) | **NEW** sanctioned-packs card | ✅ honest (reference) | **re-upload in GitHub → Settings → Social preview** (the file is fixed; the live og:image is a manual upload) |
| `mission-control-v5.svg` | Mission Control TUI | ⚠️ legacy | unreferenced now; keep as a *legacy* asset or delete |
| `frontier-scout-radar.svg`, `hero.svg`, `frontier-scout-hero.svg/.png` | old radar identity | ⚠️ legacy | do **not** reference from the README hero; ok inside a collapsed "legacy radar engine" section |
| `frontier-scout-mission-control-poster.png`, `frontier-scout-report-preview.png` | radar/report screenshots | ⚠️ legacy | only inside a `<details>`-collapsed "engine" section, clearly labelled legacy |

**New components you may want to design (specs in §8):** `divider.svg`, `features.svg` (the 3 "what you
get" cards), `install.svg` (terminal card), `safety.svg` (the static-safety explainer). All optional —
markdown tables already cover much of this honestly.

---

## 6. Recommended README structure (top → bottom)

A landing-page order that keeps the honest identity first. Anchors in parentheses must stay stable.

1. **Hero** — `hero-banner.svg` (done) full-width.
2. **Badges row** — release · Python 3.11+ · MIT · `telemetry-none` · a **`research preview`** badge
   (shields static label). One style only (`for-the-badge`).
3. **One-liner + nav** — centered: *"Repo-rank approved MCP servers → a static safety map → a Claude Code
   managed-config fragment. Research preview."* Nav: About · How it works · **Sanctioned packs** · Quickstart · Roadmap.
4. **Research-preview NOTE** (`> [!NOTE]`) — the §2 must-say lines (already in the README; keep).
5. **About** — the §1 identity; one sentence demoting the radar to "the engine underneath."
6. **How it works** — the `RANK → CHECK → EXPORT` table *or* a `steps.svg` flow graphic (§8). End with
   "No server is started or executed."
7. **What you get** — 3 honest cards (repo-ranked curation · static safety + risk-gating · managed-config
   export "emits, doesn't enforce"). Table or `features.svg`.
8. **Quickstart** — `install.svg` or a fenced `console` block; link the **[gold-path example](../examples/sanctioned-packs/)**.
9. **Safety model** — explicitly *static*: capability+policy, no execution, secrets redacted, keyless/offline.
10. **Roadmap** — lead with **Current direction — research preview**; collapse radar history in `<details>`
    (already done). Validation-gated next, only on real pull.
11. **Legacy radar engine** *(optional, collapsed `<details>`)* — the Mission Control screenshots + `demo`,
    clearly labelled "the ranking/safety engine underneath, not the product."
12. **Footer** — MIT · "research preview, not market-validated".

---

## 7. Assembly patterns (copy-paste)

**Hero (single dark SVG — Lane A):**
```html
<img src="docs/assets/hero-banner.svg" alt="Frontier Scout — sanctioned MCP-server packs for coding assistants. Repo-rank approved MCP servers, read each server's static safety map, and export the approved set into your Claude Code managed config." width="100%">
```
**Dark/light variant (Lane B):**
```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero-banner-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hero-banner-light.svg">
  <img alt="Frontier Scout — sanctioned MCP packs (research preview)" src="docs/assets/hero-banner-dark.svg" width="100%">
</picture>
```
**Two-column "what you get" (works without any SVG):**
```html
<table><tr>
<td width="33%" valign="top">

**Repo-ranked curation**
The servers that matter to _your_ code rise first — local tree-sitter, source never leaves the machine.

</td>
<td width="33%" valign="top">

**Static safety + risk-gating**
A capability + policy map per server; write/shell/credential/network can't be sanctioned without an explicit risk ack. No server is executed.

</td>
<td width="33%" valign="top">

**Managed-config export**
The approved set becomes a Claude Code `allowedMcpServers`/`deniedMcpServers` fragment an admin deploys. It emits; it doesn't enforce.

</td>
</tr></table>
```

---

## 8. SVG component specs (for new graphics)

All: `width=840` (or 1280 for full-bleed), explicit `viewBox`+`width`+`height`, system-mono, the §4 palette,
`role="img"` + honest `aria-label`, **no** `<style>/<script>/<foreignObject>/class/style`.

| Component | viewBox | Content | Notes |
|---|---|---|---|
| `divider.svg` | `0 0 1280 2` | a 1px mint→transparent line | trivial; one `<rect>` + gradient |
| `steps.svg` (flow) | `0 0 1280 220` | the RANK→CHECK→EXPORT motif from the hero, standalone | reuse hero's right-panel art |
| `features.svg` | `0 0 1280 360` | 3 cards: curation · static safety · managed-config export | mirror §7 copy; mint titles, slate body |
| `install.svg` | `0 0 1280 240` | a terminal card: `pip install frontier-scout` then `frontier-scout packs candidates …` | mac-window dots; mono; `$` prompt in muted |
| `safety.svg` | `0 0 1280 300` | "Static safety" explainer: capability chips (read/write/shell/network/credential) + "no server executed" | red only on write/shell/credential/network chips |

Optional **Lane B** animation per component (one each): divider width pulse (3s) · a single arrow dash-flow
on the steps path · a slow gradient shimmer on the wordmark. Keep `dur` 3–6s, `repeatCount="indefinite"`.

---

## 9. Copy bank (honest strings — drop into SVG/markdown)

- Eyebrow: `SANCTIONED MCP PACKS · RESEARCH PREVIEW`
- Wordmark: `FRONTIER SCOUT`
- Value prop (1 line): `Repo-rank approved MCP servers into a static safety map, then export a Claude Code managed-config fragment.`
- Value prop (short): `Sanctioned MCP packs for Claude Code` · sub: `repo-ranked · static safety · managed-config export`
- Chips: `Claude Code first · static analysis · keyless · research preview · MIT`
- Safety stamp: `Static analysis only — no MCP server was executed.`
- Export stamp: `Generated for admin review; static export, not runtime enforcement.`
- Roadmap lead: `Current direction — research preview: repo-aware sanctioned MCP-server packs for Claude Code.`
- Honesty footer: `Research preview — technically coherent, not market-validated. Human design-partner gate: 0/5.`

Acceptance grep (run on every new asset; requires `rsvg-convert` (librsvg) on PATH):
```bash
grep -icE "radar|receipt|sandbox|enforce|runtime polic|cross-client|copilot|cursor|\bdocker\b|market.?valid|\bpmf\b|see new AI|bring your own LLM" docs/assets/<file>.svg   # must be 0
rsvg-convert -w 1280 docs/assets/<file>.svg -o /tmp/check.png   # then eyeball it
```

---

## 10. Acceptance checklist (design is "done" only when all pass)

**Honesty (§2):** ☐ no banned words in any art ☐ "static / no server executed" visible somewhere in the
first viewport ☐ "research preview" + "Claude Code first" present ☐ no radar/receipt/CI-guard framing as the
product ☐ no market-validation/PMF/star-bragging.

**Identity:** ☐ first image a visitor sees is the **sanctioned-packs** story (not Mission Control) ☐ radar
demoted to a collapsed/"engine" section ☐ roadmap leads with the current direction.

**Technical:** ☐ every graphic is a baked `.svg` referenced via `<img>`/`<picture>` ☐ 0 stripped constructs
(`<style>/<script>/class/style/<foreignObject>`) ☐ well-formed XML ☐ light/dark legible (dark-bg or dual
variants) ☐ each SVG < 100KB ☐ **rendered to PNG and eyeballed** (not just code-reviewed) ☐ social card
re-uploaded in repo Settings.

**References:** structure inspired by [othneildrew/Best-README-Template](https://github.com/othneildrew/Best-README-Template) ·
component method from the `perfect-readme` skill (adapted to static SVG) · style anchor = `hero-banner.svg`
+ `frontier-scout-social-preview.svg` · honest product proof = `docs/examples/sanctioned-packs/`.
