# Frontier Scout TUI redesign — "The Briefing"

**Date:** 2026-05-29
**Status:** approved (owner delegated final decisions; build + ship autonomously)
**Target release:** v1.5.0

## Why

v1.0–v1.4 grew a tabbed "Mission Control" TUI whose centerpiece,
`tabs/scout_tab.py`, is now **1,022 lines** doing five unrelated jobs
(scope toggles, table, action buttons, guard banner, detail panel).
Real use exposed failures no test caught: actions with no visible
affordance, panels that don't refresh in a way the user notices, and a
worker that auto-fires on mount and renders "Scouting your repo…"
indefinitely so the screen looks broken. The owner's verdict:
**a TUI with zero bugs beats an ambitious-but-buggy one.**

Three forces cause those bugs, and the redesign removes all three by
construction:

1. **Shared mutable state** across widgets → state desync.
2. **Multiple regions to keep in sync** (list ↔ detail ↔ banner).
3. **Work with no defined end state** → frozen "loading forever".

It must also be **flawless at any terminal size** — a cramped VS Code
panel and a full-screen iTerm window are both first-class, and we never
know the size in advance.

## The concept: a calm briefing from your scout

Frontier Scout behaves like a calm intelligence analyst handing you a
**briefing**, one card at a time. The interaction model is wizard-style
(à la a guided conversation): low density, one focused thing on screen,
few keys to learn, and an always-present one-line **compass** telling
you exactly what you can do *right now*. This is unique to us — not a
dense lazygit/k9s cockpit, not a fuzzy-finder — and its calm linearity
is precisely what makes it testable to zero bugs.

Audience: everyone in tech, from a college student to a CTO. The first
screen must be obvious without reading docs.

## Architecture (the zero-bug foundation)

New package `frontier_scout/tui2/`, built **alongside** the existing
`tui/` and shipped as the default; the old TUI stays reachable via
`FRONTIER_SCOUT_UI=classic` (and `--ui classic`) as a one-release
safety net.

- **One immutable state.** A frozen `AppState` dataclass is the single
  source of truth. Every change produces a *new* `AppState`; nothing
  mutates in place; no widget reaches into another widget.
- **Navigation is an explicit screen stack.** Textual's screen stack
  holds a finite set: `HomeScreen`, `ExploreScreen`, `WorkingScreen`,
  `FindingsScreen`, `ActionResultScreen`, `SettingsScreen`,
  `ErrorScreen`. `Esc` always pops. No tabs, so no "which tab owns
  this" ambiguity. Each screen is one file, < 150 lines.
- **All async work is worker → message, never shared memory.** A flow
  starts a Textual `@work(thread=True)` worker. The worker emits
  `ProgressReporter` events (rendered live) and exactly one terminal
  message: `WorkDone(payload)` or `WorkFailed(error)`, marshaled to the
  UI thread via `post_message`. The UI thread never blocks. **Every
  flow is a total function**: it ends in a result screen or an error
  screen — never a frozen wait. `WorkingScreen` always offers cancel.
- **Errors are a screen, not an exception.** Any worker failure routes
  to `ErrorScreen` (what happened · what to try · `Esc` back). The UI
  can never crash to a frozen panel.

### Responsive layout (flawless at any size)

The root layout is three rows: **Header** (height 1) · **Body**
(`height: 1fr; overflow-y: auto`) · **Compass** (height 1). Because the
body always takes the remaining space and scrolls, **content can never
clip** at any width or height — the failure mode that plagues fixed
layouts is structurally impossible.

- Cards use `max-width: 80; width: 1fr` and center, so prose never
  sprawls on wide terminals and fills the width on narrow ones.
- No content uses a fixed height; everything inside Body scrolls.
- Text wraps (Textual `Static` wraps by default).
- A graceful floor: below ~24×7 we show a single "Enlarge the window"
  line instead of attempting a layout. Everything ≥ that renders.

Verified at 50×12, 72×20, 80×24, 120×40, 200×60 in tests.

## Screens

```
┌ ◉ frontier · scout  ·  📁 genai-core ─────────────────────────┐  Header (1 row)
│                                                               │
│   What would you like to do?                                  │  Body (1fr, scrolls)
│                                                               │
│   ▸ Scout my repo      newest AI tools that fit this code     │
│     Explore a tool     ask about anything, no repo needed     │
│     Settings           providers, memory, version             │
│     Quit                                                      │
│                                                               │
└ ↑↓ move · ⏎ choose · q quit ──────────────────────────────────┘  Compass (1 row)
```

- **HomeScreen** — calm menu: *Scout my repo* / *Explore a tool* /
  *Settings* / *Quit*. Selected row marked `▸`. `Enter` chooses.
- **ExploreScreen** — single input: "Name a tool, library, or URL."
  Enter runs an explore scout (no repo) → one or more cards. Serves the
  "scout without a project" selling point.
- **WorkingScreen** — calm staged progress: current stage with a
  spinner, completed stages dimmed with `✓`, elapsed seconds, and
  `Esc to cancel`. Fed by a `TuiReporter` posting `Progress` messages.
  Honest; never looks frozen.
- **FindingsScreen** — the briefing. One `Finding` per screen as a
  card: verdict ribbon · what it is · why it fits *your* repo · concerns
  (chips) · risk · next safe step. `←/→` (and `j/k`) flip; a position
  dot-trail (`● ○ ○ ○`) shows where you are. `Enter` runs the
  context-primary action; `a` opens the small more-actions menu; `o`
  opens the URL; `d` dismisses; `Esc` home.
- **ActionResultScreen** — "here's what you got": for Implement & Test,
  the summary, what you get, files changed, tests pass/fail, and the
  diff (scrollable). `Enter` keeps changes (only when passed), `Esc`
  back to the card.
- **SettingsScreen** — calm, read-mostly: provider availability dots,
  clear memory (this repo / all), version + paths. Each action shows a
  one-line confirmation inline.
- **ErrorScreen** — message + suggestion + `Esc` back.

## Card actions

The card already shows the brief, so these are the *actions*:

- **Implement & test** — primary `Enter` **when a repo is present**.
  Adopts the tool in an isolated copy (`run_implement`), runs tests,
  and shows the result. The headline v1.4 feature, now front-and-center.
- **Tell me more (fit + security)** — primary `Enter` in **explore /
  no-repo mode**. A deeper read (fit + security perspective). No repo
  changes.
- **Lab it (hermetic probe)** — install in a throwaway sandbox and run a
  probe; evidence before adopt. Works with or without a repo.
- **Dismiss** — remove + remember, so future scouts don't resurface it.
- **Open URL** (`o`) — trivial utility.

`Enter` runs the context-primary action; the rest live behind `a`.

## Data flow

`Finding` is a view-model normalized from a scout verdict dict
(`Finding.from_verdict`): `tool_name`, `verdict`
(adopt/trial/assess/hold), `fit`, `risk`, `category`, `summary`,
`why_fit`, `concerns` (slug/label/severity/evidence),
`next_step`, `url`. The TUI never reaches into raw dicts past this
boundary.

Backends are reused unchanged and TUI-agnostic:
`scout.run_scan(repo, reporter=…)`, `implement.run_implement(…)` →
`ImplementResult`, `implement.keep_changes/discard`,
`lab_runner.run`, `evaluate.evaluate_url`, `store` for memory.
The TUI provides a `TuiReporter(ProgressReporter)` that posts
`Progress` messages to the app.

## Error handling

- Worker exceptions never propagate to Textual's loop: the worker bridge
  catches everything and posts `WorkFailed(message)`.
- Cancellation: `Esc` on `WorkingScreen` cancels the worker and pops.
- Missing provider / no API key: a friendly `ErrorScreen` ("No LLM
  provider configured — run `frontier-scout setup`"), never a crash.
- Path-safety and spend invariants are already enforced in the
  backends; the TUI adds no new spend path.

## Testing strategy (how we prove zero bugs)

All via Textual `app.run_test(size=(w,h))` + `asyncio.run` (matching the
existing suite; no new deps). New file `tests/test_tui2.py`:

1. **Every screen renders** from typed sample state at 50×12, 80×24,
   120×40, 200×60 — mounts without exception, key widgets present.
2. **State machine** — Home→(Scout)→Working→Findings; Working+cancel→
   Home; Working+WorkFailed→Error; Findings→(Enter)→Working→
   ActionResult. Assert the resulting top screen each time.
3. **Compass correctness** — each screen's compass is non-empty and
   advertises an exit (`esc`/`q`).
4. **Carousel clamp** — `←` at first and `→` at last stay in range; the
   dot-trail matches the index.
5. **Error boundary** — a worker that raises lands on `ErrorScreen` and
   the app stays alive.
6. **Determinism** — `Finding.from_verdict` is a pure function with a
   stable mapping (unit-tested without the TUI).

Plus `ruff` clean across the new package and the full existing suite
staying green.

## Rollout

1. Branch `feat/v1.5.0-briefing-tui` from `main`.
2. Build `tui2/`, tests green, ruff clean.
3. Wire default: bare `frontier-scout` → Briefing; `FRONTIER_SCOUT_UI=
   classic` or `--ui classic` → old TUI for one release.
4. Bump to 1.5.0 (minor: additive, old TUI still reachable, CLI
   surface unchanged); CHANGELOG `## 1.5.0`; short README note.
5. Merge to `main` (restore-protection pattern), tag `v1.5.0`, trigger
   the release workflow.

## Out of scope (parked)

- Deleting the classic TUI (next release, once Briefing has soaked).
- Mouse-first interactions (keyboard + basic click only).
- Live-streaming activity log on the working screen (staged line is
  enough; revisit if users want detail).
- Multi-repo workspace, saved filters, themes beyond the single default.
```
